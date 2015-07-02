import os
import os.path
import functools
from ConfigParser import ConfigParser
from SoftLayer.API import Client
from SoftLayer.managers.dns import DNSManager

from .records import Record


def memoize(f):
    f.cache = {}

    def wrapped(*args, **kwargs):
        if kwargs:
            key = args, kwargs.items()
        else:
            key = args
        if key not in f.cache:
            f.cache[key] = f(*args, **kwargs)
        return f.cache[key]
    functools.update_wrapper(wrapped, f)
    return wrapped


class SoftLayerInterface(object):
    """
    Interface to the SoftLayer DNS API.

    TODO
    - Use bulk update methods for performance.
    """

    def __init__(self, eager=False):
        self.eager = eager
        config = ConfigParser()
        config.read(os.path.join(os.getenv('HOME'), '.softlayer'))
        self.api_username = config.get('auth', 'api_username')
        self.api_key = config.get('auth', 'api_key')

    @property
    @memoize
    def client(self):
        return Client(username=self.api_username, api_key=self.api_key)

    @property
    @memoize
    def dns(self):
        return DNSManager(self.client)

    @memoize
    def _get_domains_raw(self):
        return self.dns.list_zones()

    @memoize
    def _get_domains_map(self):
        ret = {}
        for d in self._get_domains_raw():
            ret[d['name']] = d['id']
        return ret

    @memoize
    def _get_domains_by_name(self):
        by_name = {}
        for domain in self._get_domains_raw():
            by_name[domain['name']] = domain
        return by_name

    def _record_to_dict(self, record):
        return {'host': record.host,
                'data': record.data,
                'type': record.type,
                'ttl': record.ttl,
                'mxPriority': record.priority}

    def _dict_to_record(self, d):
        return Record.create(type=d['type'],
                             host=d['host'],
                             data=d['data'],
                             ttl=d['ttl'],
                             priority=d['mxPriority'],
                             ref=d['id'])

    @memoize
    def get_domains(self):
        return [d['name'] for d in self._get_domains_raw()]

    @memoize
    def get_records(self, name):
        try:
            domain = self._get_domains_by_name()[name]
        except KeyError:
            return []
        recs = self.dns.get_records(domain['id'])
        return [self._dict_to_record(rec) for rec in recs
                if rec['type'] != 'soa']

    def _delete_record(self, name, record):
        # self.dns.delete_record fails to return a success indicator, so bypass it.
        return self.dns.record.deleteObject(id=record.ref)

    def _update_record(self, name, old_record, new_record):
        # self.dns.edit_record fails to return a success indicator, so bypass it.
        return self.dns.record.editObject(
            self._record_to_dict(new_record), id=old_record.ref)

    def _create_record(self, name, record):
        # self.dns.create_record doesn't support mxPriority, so bypass it.
        domain_id = self._get_domains_by_name()[name]['id']
        obj = {
            'domainId': domain_id,
            'ttl': record.ttl,
            'host': record.host,
            'type': record.type,
            'data': record.data,
        }
        if record.type == 'mx':
            obj['mxPriority'] = record.priority
        return self.dns.record.createObject(obj)

    def delete_records(self, name, records):
        return all(self._delete_record(name, record) for record in records)

    def update_records(self, name, changelist):
        return all(self._update_record(name, old, new)
                   for old, new in changelist)

    def create_records(self, name, records):
        return all(self._create_record(name, record) for record in records)

    def create_domain(self, name):
        ret = self.dns.create_zone(name)
        # un-memoize so we can fetch the new domain's info after this.
        self._get_domains_raw(self).cache = {}
        return ret

