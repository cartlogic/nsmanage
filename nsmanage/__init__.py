"""
DNS management tools
- manage diff [domains]
    Downloads all records (optionally restricted by domain) and compares to the
    current state reflected in the repo.
- manage push [domains]
    Updates all live records to the current state reflected in the repo.
- manage lint [domains]
    Just check the current config for the given domains.

FIXME
- Use bulk update methods for performance
- Add more linting features
- Add warning when TTLs are adjusted to deal with softlayer bug
- Support other providers?
    - softlayer
    - rackspace
    - linode
    - easydns
    - dynect
"""

import argparse
import functools
import sys
import os
import os.path
from operator import attrgetter
from ConfigParser import ConfigParser
from SoftLayer.API import Client

from .records import Domain, Record, A, CNAME, MX, TXT, NS, AAAA, SPF


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
        if self.eager or True:  # FIXME
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


class Manager(object):

    def __init__(self, interface, verbose=False):
        self.interface = interface
        self.verbose = verbose

    def load_domain_config(self, name):
        mod_name = name.lower().replace('.', '_')
        __import__(mod_name)
        return sys.modules[mod_name].domain

    def sort_records(self, records):
        "Sort a list of records, in-place, in a canonical way."
        for key in ('data', 'host', 'priority', 'type'):
            records.sort(key=attrgetter(key))

    def diff_record_lists(self, old, new):
        """
        Given two lists of records that are assumed to be sorted and
        normalized, return:

            1. Records added -> list of new records
            2. Records removed -> list of old records
            3. Records changed -> list of (old, new) record tuples
        """
        added = []
        changed = []
        removed = list(old)

        def find_match(newrec, level):
            for oldrec in removed:
                if oldrec.match(newrec, level):
                    removed.remove(oldrec)
                    if oldrec.diff(newrec, level):
                        changed.append((oldrec, newrec))
                    return True
            else:
                return False

        for newrec in new:
            # Try to find a matching old record, using gradually decreasing
            # specificity.
            for level in range(5):
                if find_match(newrec, level):
                    break
            else:
                # If we still didn't find a matching old record, this is a new
                # record.
                added.append(newrec)

        return added, removed, changed

    def lint(self, name):
        "Check the configuration for this domain locally."
        domain = self.load_domain_config(name)
        domain.add_softlayer_ns_records()
        return domain.to_records()

    def diff(self, name):
        """
        Print the difference between the current live state of this domain
        and the state defined in the configuration.

        Implicitly runs a lint() as well.
        """
        remote_recs = self.interface.get_records(name)
        self.sort_records(remote_recs)

        local_recs = self.lint(name)
        self.sort_records(local_recs)

        added, removed, changed = self.diff_record_lists(remote_recs,
                                                         local_recs)

        if added:
            print "*** RECORDS ADDED ***"
        for rec in added:
            print "+++ %s" % rec

        if removed:
            print "*** RECORDS REMOVED ***"
        for rec in removed:
            print "--- %s" % rec

        if changed:
            print "*** RECORDS CHANGED ***"
        for oldrec, newrec in changed:
            print "--- %s" % oldrec
            print "+++ %s" % newrec

        if self.verbose and not (added or removed or changed):
            print "No differences, live state and config state are in sync."

        return added, removed, changed

    def push(self, name):
        """
        Push the local configuration for this domain to the remote host.
        Implicitly runs a lint() and a diff() on this domain.
        """
        # Get the unsynced differences via diff().
        added, removed, changed = self.diff(name)

        for rec in added:
            if self.verbose:
                print "ADDING\n%s" % rec
        if not self.interface.create_records(name, added):
            print "Failed adding records."

        for rec in removed:
            if self.verbose:
                print "REMOVING\n%s" % rec
        if not self.interface.delete_records(name, removed):
            print "Failed removing records."

        for oldrec, newrec in changed:
            if self.verbose:
                print "UPDATING\n%s\nto\%s" % (oldrec, newrec)
        if not self.interface.update_records(name, changed):
            print "Failed updating records."


def main():
    p = argparse.ArgumentParser(description='Manage DNS records.')
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   help='print detailed output')
    p.add_argument('-p', '--provider', dest='provider',
                   type=str,
                   default='softlayer',
                   choices=('softlayer,'),
                   help='DNS provider')
    p.add_argument('action', type=str,
                   help='action to perform',
                   choices=('lint', 'diff', 'push'))
    p.add_argument('domains', metavar='domain', type=str, nargs='*',
                   help='domains to manage records on (default to all)')
    args = p.parse_args()
    print "Running %s for %s" % (args.action,
                                 ', '.join(args.domains)
                                 if args.domains else
                                 'all domains')

    sys.path.insert(0, os.getcwd())

    if args.provider == 'softlayer':
        interface = SoftLayerInterface(eager=(not args.domains))

    if not args.domains:
        args.domains = interface.get_domains()
        all = True
    else:
        all = False

    manager = Manager(interface, verbose=args.verbose)

    for name in args.domains:
        if all and args.verbose:
            print "Processing %s" % name
        getattr(manager, args.action)(name)


if __name__ == '__main__':
    main()
