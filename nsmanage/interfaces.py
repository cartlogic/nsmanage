import os
import os.path
import functools
from ConfigParser import ConfigParser
from SoftLayer.API import Client

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

    def _api_client(self, type, id):
        return Client(type, id, self.api_username, self.api_key)

    def _account_client(self):
        return self._api_client('SoftLayer_Account', None)

    def _domain_client(self, name):
        domain_id = self._get_domains_map()[name]
        return self._api_client('SoftLayer_Dns_Domain', domain_id)

    def _record_client(self, record_id):
        return self._api_client('SoftLayer_Dns_Domain_ResourceRecord',
                                record_id)

    @memoize
    def _get_domains_raw(self):
        client = self._account_client()
        client.set_object_mask({'domains': {'resourceRecords': {}}})
        resp = client.getObject()
        return resp['domains']

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
        recs = self._get_domains_by_name()[name]['resourceRecords']
        return [self._dict_to_record(rec) for rec in recs
                if rec['type'] != 'soa']

    def _delete_record(self, name, record):
        rc = self._record_client(record.ref)
        return rc.deleteObject()

    def _update_record(self, name, old_record, new_record):
        rc = self._record_client(old_record.ref)
        return rc.editObject(self._record_to_dict(new_record))

    def _create_record(self, name, record):
        dc = self._domain_client(name)
        method = 'create%sRecord' % record.type.capitalize()
        args = [record.host, record.data, record.ttl]
        if record.type == 'mx':
            args.append(record.priority)
        return getattr(dc, method)(*args)

    def delete_records(self, name, records):
        return all(self._delete_record(name, record) for record in records)

    def update_records(self, name, changelist):
        return all(self._update_record(name, old, new)
                   for old, new in changelist)

    def create_records(self, name, records):
        return all(self._create_record(name, record) for record in records)


