#!/usr/bin/env python
# -*- coding: UTF-8 -*-

#  Licensed to the Apache Software Foundation (ASF) under one
#  or more contributor license agreements.  See the NOTICE file
#  distributed with this work for additional information
#  regarding copyright ownership.  The ASF licenses this file
#  to you under the Apache License, Version 2.0 (the
#  "License"); you may not use this file except in compliance
#  with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing,
#  software distributed under the License is distributed on an
#  "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#  KIND, either express or implied.  See the License for the
#  specific language governing permissions and limitations
#  under the License.
from datetime import datetime
from _sqlite3 import OperationalError, IntegrityError
import unittest
from bhrelations.api import (EnvironmentSetup, RelationsSystem,
                             TicketRelationsSpecifics)
from bhrelations.tests.mocks import TestRelationChangingListener
from bhrelations.validation import ValidationError
from multiproduct.env import ProductEnvironment
from tests.env import MultiproductTestCase
from trac.ticket.model import Ticket
from trac.test import EnvironmentStub, Mock
from trac.core import TracError
from trac.util.datefmt import utc

try:
    from babel import Locale

    locale_en = Locale.parse('en_US')
except ImportError:
    locale_en = None


class BaseApiApiTestCase(MultiproductTestCase):
    def setUp(self):
        env = EnvironmentStub(
            default_data=True,
            enable=['trac.*', 'multiproduct.*', 'bhrelations.*']
        )
        env.config.set('bhrelations', 'global_validators',
                       'NoSelfReferenceValidator,ExclusiveValidator,'
                       'BlockerValidator')
        config_name = RelationsSystem.RELATIONS_CONFIG_NAME
        env.config.set(config_name, 'dependency', 'dependson,dependent')
        env.config.set(config_name, 'dependency.validators',
                       'NoCycles,SingleProduct')
        env.config.set(config_name, 'dependson.blocks', 'true')
        env.config.set(config_name, 'parent_children', 'parent,children')
        env.config.set(config_name, 'parent_children.validators',
                       'OneToMany,SingleProduct,NoCycles')
        env.config.set(config_name, 'children.label', 'Overridden')
        env.config.set(config_name, 'parent.copy_fields',
                       'summary, foo')
        env.config.set(config_name, 'parent.exclusive', 'true')
        env.config.set(config_name, 'multiproduct_relation', 'mprel,mpbackrel')
        env.config.set(config_name, 'oneway', 'refersto')
        env.config.set(config_name, 'duplicate', 'duplicateof,duplicatedby')
        env.config.set(config_name, 'duplicate.validators', 'ReferencesOlder')
        env.config.set(config_name, 'duplicateof.label', 'Duplicate of')
        env.config.set(config_name, 'duplicatedby.label', 'Duplicated by')
        env.config.set(config_name, 'blocker', 'blockedby,blocks')
        env.config.set(config_name, 'blockedby.blocks', 'true')

        self.global_env = env
        self._upgrade_mp(self.global_env)
        self._setup_test_log(self.global_env)
        self._load_product_from_data(self.global_env, self.default_product)
        self.env = ProductEnvironment(self.global_env, self.default_product)

        self.req = Mock(href=self.env.href, authname='anonymous', tz=utc,
                        args=dict(action='dummy'),
                        locale=locale_en, lc_time=locale_en)
        self.relations_system = RelationsSystem(self.env)
        self._upgrade_env()

    def tearDown(self):
        self.global_env.reset_db()

    def _upgrade_env(self):
        environment_setup = EnvironmentSetup(self.env)
        try:
            environment_setup.upgrade_environment(self.env.db_transaction)
        except OperationalError:
            # table remains but database version is deleted
            pass

    @classmethod
    def _insert_ticket(cls, env, summary, **kw):
        """Helper for inserting a ticket into the database"""
        ticket = Ticket(env)
        ticket["Summary"] = summary
        for k, v in kw.items():
            ticket[k] = v
        return ticket.insert()

    def _insert_and_load_ticket(self, summary, **kw):
        return Ticket(self.env, self._insert_ticket(self.env, summary, **kw))

    def _insert_and_load_ticket_with_env(self, env, summary, **kw):
        return Ticket(env, self._insert_ticket(env, summary, **kw))


class ApiTestCase(BaseApiApiTestCase):
    def test_can_add_two_ways_relations(self):
        #arrange
        ticket = self._insert_and_load_ticket("A1")
        dependent = self._insert_and_load_ticket("A2")
        #act
        relations_system = self.relations_system
        relations_system.add(
            ticket, dependent, "dependent")
        #assert
        relations = relations_system.get_relations(ticket)
        self.assertEqual("dependent", relations[0]["type"])
        self.assertEqual(unicode(dependent.id), relations[0]["destination"].id)

        relations = relations_system.get_relations(dependent)
        self.assertEqual("dependson", relations[0]["type"])
        self.assertEqual(unicode(ticket.id), relations[0]["destination"].id)

    def test_can_add_single_way_relations(self):
        #arrange
        ticket = self._insert_and_load_ticket("A1")
        referred = self._insert_and_load_ticket("A2")
        #act
        relations_system = self.relations_system
        relations_system.add(ticket, referred, "refersto")
        #assert
        relations = relations_system.get_relations(ticket)
        self.assertEqual("refersto", relations[0]["type"])
        self.assertEqual(unicode(referred.id), relations[0]["destination"].id)

        relations = relations_system.get_relations(referred)
        self.assertEqual(0, len(relations))

    def test_can_add_multiple_relations(self):
        #arrange
        ticket = self._insert_and_load_ticket("A1")
        dependent1 = self._insert_and_load_ticket("A2")
        dependent2 = self._insert_and_load_ticket("A3")
        #act
        relations_system = self.relations_system
        relations_system.add(
            ticket, dependent1, "dependent")
        relations_system.add(
            ticket, dependent2, "dependent")
        #assert
        relations = relations_system.get_relations(ticket)
        self.assertEqual(2, len(relations))

    def test_will_not_create_more_than_one_identical_relations(self):
        #arrange
        ticket = self._insert_and_load_ticket("A1")
        dependent1 = self._insert_and_load_ticket("A2")
        #act
        relations_system = self.relations_system
        relations_system.add(
            ticket, dependent1, "dependent")
        self.assertRaisesRegexp(
            TracError,
            "already exists",
            relations_system.add,
            ticket, dependent1, "dependent")

    def test_will_not_create_more_than_one_identical_relations_db_level(self):
        sql = """INSERT INTO bloodhound_relations (source, destination, type)
                    VALUES (%s, %s, %s)"""
        with self.env.db_transaction as db:
            db(sql, ["1", "2", "dependson"])
            self.assertRaises(
                IntegrityError, db, sql, ["1", "2", "dependson"])

    def test_can_add_one_way_relations(self):
        #arrange
        ticket = self._insert_and_load_ticket("A1")
        referred_ticket = self._insert_and_load_ticket("A2")
        #act
        relations_system = self.relations_system
        relations_system.add(
            ticket, referred_ticket, "refersto")
        #assert
        relations = relations_system.get_relations(ticket)
        self.assertEqual("refersto", relations[0]["type"])
        self.assertEqual(unicode(referred_ticket.id),
                         relations[0]["destination"].id)

        relations = relations_system.get_relations(referred_ticket)
        self.assertEqual(0, len(relations))

    def test_can_delete_two_ways_relation(self):
        #arrange
        ticket = self._insert_and_load_ticket("A1")
        dependent_ticket = self._insert_and_load_ticket("A2")
        relations_system = self.relations_system
        relations_system.add(
            ticket, dependent_ticket, "dependson")
        relations = relations_system.get_relations(ticket)
        self.assertEqual(1, len(relations))
        #act
        relation_to_delete = relations[0]
        relations_system.delete(relation_to_delete["relation_id"])
        #assert
        relations = relations_system.get_relations(ticket)
        self.assertEqual(0, len(relations))

    def test_can_delete_single_way_relation(self):
        #arrange
        ticket = self._insert_and_load_ticket("A1")
        referred = self._insert_and_load_ticket("A2")
        #act
        relations_system = self.relations_system
        relations_system.add(ticket, referred, "refersto")

        ticket = self._insert_and_load_ticket("A1")
        dependent_ticket = self._insert_and_load_ticket("A2")
        relations_system = self.relations_system
        relations_system.add(
            ticket, dependent_ticket, "dependson")
        relations = relations_system.get_relations(ticket)

        self.assertEqual(1, len(relations))
        reverted_relations = relations_system.get_relations(dependent_ticket)
        self.assertEqual(1, len(reverted_relations))
        #act
        # self._debug_select()
        relation_to_delete = relations[0]
        relations_system.delete(relation_to_delete["relation_id"])
        #assert
        relations = relations_system.get_relations(ticket)
        self.assertEqual(0, len(relations))
        reverted_relations = relations_system.get_relations(dependent_ticket)
        self.assertEqual(0, len(reverted_relations))

    def test_can_not_add_cycled_immediate_relations(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        #act
        relations_system = self.relations_system
        relations_system.add(ticket1, ticket2, "dependson")

        try:
            relations_system.add(ticket2, ticket1, "dependson")
            self.fail("Should throw an exception")
        except ValidationError as ex:
            self.assertSequenceEqual(
                ["tp1:ticket:2", "tp1:ticket:1"], ex.failed_ids)

    def test_can_add_more_depends_ons(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        ticket3 = self._insert_and_load_ticket("A3")
        #act
        relations_system = self.relations_system
        relations_system.add(ticket1, ticket2, "dependson")
        relations_system.add(ticket1, ticket3, "dependson")

    def test_can_not_add_cycled_in_different_direction(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        #act
        relations_system = self.relations_system
        relations_system.add(ticket1, ticket2, "dependson")
        self.assertRaises(
            ValidationError,
            relations_system.add,
            ticket1,
            ticket2,
            "dependent")

    def test_can_not_add_cycled_relations(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        ticket3 = self._insert_and_load_ticket("A3")
        #act
        relations_system = self.relations_system
        relations_system.add(ticket1, ticket2, "dependson")
        relations_system.add(ticket2, ticket3, "dependson")
        self.assertRaises(
            ValidationError,
            relations_system.add,
            ticket3,
            ticket1,
            "dependson")

    def test_can_not_add_more_than_one_parents(self):
        #arrange
        child = self._insert_and_load_ticket("A1")
        parent1 = self._insert_and_load_ticket("A2")
        parent2 = self._insert_and_load_ticket("A3")
        #act
        relations_system = self.relations_system
        relations_system.add(child, parent1, "parent")
        self.assertRaises(
            ValidationError,
            relations_system.add,
            child,
            parent2,
            "parent")

    def test_can_not_add_more_than_one_parents_via_children(self):
        #arrange
        child = self._insert_and_load_ticket("A1")
        parent1 = self._insert_and_load_ticket("A2")
        parent2 = self._insert_and_load_ticket("A3")
        #act
        relations_system = self.relations_system
        relations_system.add(parent1, child, "children")
        self.assertRaises(
            ValidationError,
            relations_system.add,
            parent2,
            child,
            "children")

    def test_ticket_can_be_resolved(self):
        #arrange
        child = self._insert_and_load_ticket("A1")
        parent1 = self._insert_and_load_ticket("A2")
        parent2 = self._insert_and_load_ticket("A3")
        #act
        relations_system = self.relations_system
        relations_system.add(parent1, child, "children")
        self.assertRaises(
            ValidationError,
            relations_system.add,
            parent2,
            child,
            "children")

    def test_can_save_and_load_relation_time(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        #act
        time = datetime.now(utc)
        self.relations_system.add(ticket1, ticket2, "dependent", when=time)
        relations = self.relations_system.get_relations(ticket1)
        #assert
        self.assertEqual(time, relations[0]["when"])

    def test_cannot_resolve_ticket_when_blocker_is_unresolved(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        self.relations_system.add(ticket1, ticket2, "dependson")
        #act
        self.req.args["action"] = 'resolve'
        warnings = TicketRelationsSpecifics(self.env).validate_ticket(
            self.req, ticket1)
        #asset
        self.assertEqual(1, len(list(warnings)))

    def test_can_resolve_ticket_when_blocker_is_resolved(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2", status="closed")
        self.relations_system.add(ticket1, ticket2, "dependson")
        #act
        self.req.args["action"] = 'resolve'
        warnings = TicketRelationsSpecifics(self.env).validate_ticket(
            self.req, ticket1)
        #assert
        self.assertEqual(0, len(list(warnings)))

    def test_that_relations_are_deleted_when_ticket_is_deleted(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        relations_system = self.relations_system
        relations_system.add(ticket1, ticket2, "dependent")
        self.assertEqual(1, len(relations_system.get_relations(ticket2)))
        #act
        ticket1.delete()
        #assert
        self.assertEqual(0, len(relations_system.get_relations(ticket2)))

    def test_that_no_error_when_deleting_ticket_without_relations(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        #act
        ticket1.delete()

    def test_can_add_multi_product_relations(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")

        product2 = "tp2"
        self._load_product_from_data(self.global_env, product2)
        p2_env = ProductEnvironment(self.global_env, product2)
        ticket2 = self._insert_and_load_ticket_with_env(p2_env, "A2")
        relations_system = self.relations_system
        #act
        relations_system.add(ticket1, ticket2, "mprel")
        #assert
        self.assertEqual(1, len(relations_system.get_relations(ticket1)))
        self.assertEqual(1, len(relations_system.get_relations(ticket2)))

    def _debug_select(self):
        """
        used for debug purposes
        """
        print " source, destination, type"
        sql = "SELECT source, destination, type FROM bloodhound_relations"
        with self.env.db_query as db:
            # for row in db(sql, ("source", "destination", "type")):
            for row in db(sql):
                print row

    def test_parent_relation_is_incompatible_with_two_way_relations(self):
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        self.relations_system.add(ticket1, ticket2, "dependent")

        self.assertRaises(
            ValidationError,
            self.relations_system.add,
            ticket1,
            ticket2,
            "parent")
        self.assertRaises(
            ValidationError,
            self.relations_system.add,
            ticket1,
            ticket2,
            "children")

    def test_parent_relation_is_incompatible_with_one_way_relations(self):
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        self.relations_system.add(ticket1, ticket2, "refersto")

        self.assertRaises(
            ValidationError,
            self.relations_system.add,
            ticket1,
            ticket2,
            "parent")
        self.assertRaises(
            ValidationError,
            self.relations_system.add,
            ticket1,
            ticket2,
            "children")

    def test_parent_must_be_in_same_product(self):
        ticket1 = self._insert_and_load_ticket("A1")
        product2 = "tp2"
        self._load_product_from_data(self.global_env, product2)
        p2_env = ProductEnvironment(self.global_env, product2)
        ticket2 = self._insert_and_load_ticket_with_env(p2_env, "A2")

        self.assertRaises(
            ValidationError,
            self.relations_system.add,
            ticket1, ticket2, "parent"
        )
        self.assertRaises(
            ValidationError,
            self.relations_system.add,
            ticket1, ticket2, "children"
        )

    def test_cannot_create_other_relations_between_descendants(self):
        t1, t2, t3, t4, t5 = map(self._insert_and_load_ticket, range(5))
        self.relations_system.add(t4, t2, "parent")  #    t1 -> t2
        self.relations_system.add(t3, t2, "parent")  #         /  \
        self.relations_system.add(t2, t1, "parent")  #       t3    t4

        self.assertRaises(
            ValidationError,
            self.relations_system.add, t1, t2, "dependent"
        )
        self.assertRaises(
            ValidationError,
            self.relations_system.add, t2, t1, "dependent"
        )
        self.assertRaises(
            ValidationError,
            self.relations_system.add, t1, t4, "dependent"
        )
        self.assertRaises(
            ValidationError,
            self.relations_system.add, t3, t1, "dependent"
        )
        try:
            self.relations_system.add(t1, t5, "dependent")
            self.relations_system.add(t3, t4, "dependent")
        except ValidationError:
            self.fail("Could not add valid relation.")

    def test_cannot_add_parent_if_this_would_cause_invalid_relations(self):
        t1, t2, t3, t4, t5 = map(self._insert_and_load_ticket, range(5))
        self.relations_system.add(t4, t2, "parent")  #    t1 -> t2
        self.relations_system.add(t3, t2, "parent")  #         /  \
        self.relations_system.add(t2, t1, "parent")  #       t3    t4    t5
        self.relations_system.add(t2, t5, "dependent")

        self.assertRaises(
            ValidationError,
            self.relations_system.add, t5, t2, "parent"
        )
        self.assertRaises(
            ValidationError,
            self.relations_system.add, t5, t3, "parent"
        )
        self.assertRaises(
            ValidationError,
            self.relations_system.add, t1, t5, "parent"
        )
        try:
            self.relations_system.add(t5, t1, "parent")
        except ValidationError:
            self.fail("Could not add valid relation.")

    def test_cannot_close_ticket_with_open_children(self):
        t1 = self._insert_and_load_ticket("1", status='closed')
        t2 = self._insert_and_load_ticket("2", status='closed')
        t3 = self._insert_and_load_ticket("3")
        self.relations_system.add(t2, t1, "parent")
        self.relations_system.add(t3, t1, "parent")

        self.req.args["action"] = 'resolve'
        warnings = TicketRelationsSpecifics(self.env).validate_ticket(
            self.req, t1)
        #assert
        self.assertEqual(1, len(list(warnings)))

    def test_duplicate_can_only_reference_older_ticket(self):
        t1 = self._insert_and_load_ticket("1")
        t2 = self._insert_and_load_ticket("2")

        self.assertRaises(
            ValidationError,
            self.relations_system.add,
            t1,
            t2,
            "duplicateof",
        )
        self.relations_system.add(t2, t1, "duplicateof")

    def test_detects_blocker_cycles(self):
        t1, t2, t3, t4, t5 = map(self._insert_and_load_ticket, range(5))
        self.relations_system.add(t1, t2, "blocks")
        self.relations_system.add(t3, t2, "dependson")
        self.relations_system.add(t4, t3, "blockedby")
        self.relations_system.add(t4, t5, "dependent")

        self.assertRaises(ValidationError,
                          self.relations_system.add, t2, t1, "blocks")
        self.assertRaises(ValidationError,
                          self.relations_system.add, t3, t1, "dependent")
        self.assertRaises(ValidationError,
                          self.relations_system.add, t1, t2, "blockedby")
        self.assertRaises(ValidationError,
                          self.relations_system.add, t1, t5, "dependson")

        self.relations_system.add(t1, t2, "dependent")
        self.relations_system.add(t2, t3, "blocks")
        self.relations_system.add(t4, t3, "dependson")
        self.relations_system.add(t5, t4, "blockedby")

        self.relations_system.add(t1, t2, "refersto")
        self.relations_system.add(t2, t1, "refersto")


class RelationChangingListenerTestCase(BaseApiApiTestCase):
    def test_can_sent_adding_event(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        relations_system = self.relations_system
        test_changing_listener = self.env[TestRelationChangingListener]
        #act
        relations_system.add(ticket1, ticket2, "dependent")
        #assert
        self.assertEqual("adding_relation", test_changing_listener.action)
        relation = test_changing_listener.relation
        self.assertEqual("dependent", relation.type)

    def test_can_sent_deleting_event(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        relations_system = self.relations_system
        test_changing_listener = self.env[TestRelationChangingListener]
        relations_system.add(ticket1, ticket2, "dependent")
        #act
        relations = relations_system.get_relations(ticket1)
        relation_to_delete = relations[0]
        relations_system.delete(relation_to_delete["relation_id"])
        #assert
        self.assertEqual("deleting_relation", test_changing_listener.action)
        relation = test_changing_listener.relation
        self.assertEqual("dependent", relation.type)


class TicketChangeRecordUpdaterTestCase(BaseApiApiTestCase):
    def test_can_update_ticket_history_on_relation_add_on(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        relations_system = self.relations_system
        #act
        relations_system.add(ticket1, ticket2, "dependent")
        #assert
        change_log1 = Ticket(self.env, ticket1.id).get_changelog()
        self.assertEquals(1, len(change_log1))

        change_log2 = Ticket(self.env, ticket2.id).get_changelog()
        self.assertEquals(1, len(change_log2))

    def test_can_update_ticket_history_on_relation_deletion(self):
        #arrange
        ticket1 = self._insert_and_load_ticket("A1")
        ticket2 = self._insert_and_load_ticket("A2")
        relations_system = self.relations_system
        relations_system.add(ticket1, ticket2, "dependent")
        relations = relations_system.get_relations(ticket1)
        #act
        relation_to_delete = relations[0]
        relations_system.delete(relation_to_delete["relation_id"])
        #assert
        change_log1 = Ticket(self.env, ticket1.id).get_changelog()
        self.assertEquals(2, len(change_log1))

        change_log2 = Ticket(self.env, ticket2.id).get_changelog()
        self.assertEquals(2, len(change_log2))

    def _debug_select(self, ticket_id=None):
        """
        used for debug purposes
        """
        # print " source, destination, type"
        sql = "SELECT * FROM ticket_change"
        print "db_direct_transaction result:"
        with self.env.db_direct_transaction as db:
            # for row in db(sql, ("source", "destination", "type")):
            for row in db(sql):
                print row

        sql = "SELECT * FROM ticket_change"
        print "db_transaction result:"
        with self.env.db_transaction as db:
            for row in db(sql):
                print row

        if ticket_id:
            sql = """SELECT time, author, field, oldvalue, newvalue
                    FROM ticket_change WHERE ticket=%s"""
            print "db_transaction select by ticket_id result:"
            with self.env.db_transaction:
                for row in self.env.db_query(sql, (ticket_id, )):
                    print row


def suite():
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(ApiTestCase, 'test'))
    test_suite.addTest(unittest.makeSuite(
        RelationChangingListenerTestCase, 'test'))
    test_suite.addTest(unittest.makeSuite(
        TicketChangeRecordUpdaterTestCase, 'test'))
    return test_suite


if __name__ == '__main__':
    unittest.main()