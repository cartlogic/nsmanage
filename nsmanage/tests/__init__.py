import sys
import os.path
from collections import defaultdict
from unittest import TestCase

from nsmanage import Manager, NS, A, AAAA, CNAME, MX, TXT, SPF

__here__ = os.path.dirname(__file__)
sys.path.insert(0, __here__)


class TestInterface(object):

    def __init__(self):
        self.calls = defaultdict(list)

    def get_domains(self):
        return ['foo.com', 'bar.com']

    def get_records(self, name):
        return {'foo.com': [A('@', '8.2.2.4', ttl=1200),
                            A('foo', '80.123.65.79'),
                            CNAME('www', '@', ttl=23200),
                            CNAME('blah', 'quux', tlt=4732),
                            MX('@', 'mail1.mail.com', ttl=7200),
                            MX('@', 'mail2.mail.com', ttl=7200)],
                'bar.com': [A('@', '1.2.3.4'),
                            A('foo', '8.2.2.2', ttl=1200),
                            A('bar', '92.234.12.1'),
                            CNAME('www', '@')]}[name]

    def delete_records(self, name, records):
        self.calls['delete'].append((name, records))
        return True

    def create_records(self, name, records):
        self.calls['create'].append((name, records))
        return True

    def update_records(self, name, changelist):
        self.calls['update'].append((name, changelist))
        return True


class TestApp(TestCase):

    def test_push(self):
        interface = TestInterface()
        manager = Manager(interface)
        manager.push('foo.com')

        self.assertEqual(len(interface.calls['create']), 1)
        self.assertEqual(len(interface.calls['update']), 1)
