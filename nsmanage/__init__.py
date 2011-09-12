"""
TODO
- Add more linting features
- Add pull feature
- Add warning when TTLs are adjusted to deal with softlayer bug
- Support other providers?
    - softlayer
    - rackspace
    - linode
    - easydns
    - dynect
"""

import argparse
import sys
import os
from operator import attrgetter

from . import interfaces
from .records import Domain, Record, A, CNAME, MX, TXT, NS, AAAA, SPF


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
        interface = interfaces.SoftLayerInterface(eager=(not args.domains))

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
