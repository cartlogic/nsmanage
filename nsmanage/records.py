class Domain(object):

    def __init__(self, *records):
        self.records = list(records)

    def to_records(self):
        """
        Hacky replacement for to_records() to work around the SoftLayer bug
        that prevents setting different TTLs for the same host.
        """
        lowest_ttls = {}  # host -> ttl
        for rec in self.records:
            if rec.host in lowest_ttls:
                lowest_ttls[rec.host] = min(lowest_ttls[rec.host], rec.ttl)
            else:
                lowest_ttls[rec.host] = rec.ttl

        ret = []
        for rec in self.records:
            d = Record.create(host=rec.host,
                              data=rec.data,
                              ttl=lowest_ttls[rec.host],
                              type=rec.type,
                              priority=rec.priority)
            ret.append(d)

        return ret

    def add_softlayer_ns_records(self):
        self.records.extend([
            NS('@', 'ns1.softlayer.com.'),
            NS('@', 'ns2.softlayer.com.')
        ])

    def add_google_apps_records(domain):
        domain.records.extend([
            CNAME('webmail', 'ghs.google.com.'),
            MX('@', 'aspmx.l.google.com.', priority=10),
            MX('@', 'alt1.aspmx.l.google.com.', priority=20),
            MX('@', 'alt2.aspmx.l.google.com.', priority=20),
            MX('@', 'aspmx2.googlemail.com.', priority=30),
            MX('@', 'aspmx3.googlemail.com.', priority=30),
            MX('@', 'aspmx4.googlemail.com.', priority=30),
            MX('@', 'aspmx5.googlemail.com.', priority=30),
        ])


class Record(object):
    default_ttl = 86400
    default_priority = ''
    fields = ('priority', 'ttl', 'data', 'type', 'host')

    def __init__(self, host, data, **kwargs):
        self.data = data
        self.host = host
        self.ttl = kwargs.get('ttl', self.default_ttl)
        self.priority = ''
        self.ref = kwargs.get('ref')

    @staticmethod
    def create(*args, **kwargs):
        klass = {'ns': NS,
                 'a': A,
                 'aaaa': AAAA,
                 'mx': MX,
                 'cname': CNAME,
                 'txt': TXT}[kwargs['type']]
        return klass(*args, **kwargs)

    def match(self, other, level):
        return all(getattr(self, key) == getattr(other, key) for key in
                   self.fields[level:])

    def diff(self, other, level):
        ret = {}
        for key in self.fields[:level]:
            if getattr(self, key) != getattr(other, key):
                ret[key] = (getattr(self, key), getattr(other, key))
        return ret

    def __str__(self):
        rectype = self.type.upper()
        if rectype == 'MX':
            rectype += " %d" % self.priority
        d = {'host': self.host.ljust(30),
             'ttl': ("%d" % self.ttl).ljust(9),
             'data': self.data,
             'type': rectype.ljust(6)}
        return "%(host)s %(ttl)s IN %(type)s %(data)s" % d


class NS(Record):
    type = 'ns'


class MX(Record):
    type = 'mx'

    def __init__(self, host, data, **kwargs):
        Record.__init__(self, host, data, **kwargs)
        self.priority = kwargs.get('priority', self.default_priority)


class A(Record):
    type = 'a'


class CNAME(Record):
    type = 'cname'


class TXT(Record):
    type = 'txt'


class AAAA(Record):
    type = 'aaaa'


class SPF(TXT):

    def __init__(self, host, mx=None, a=None, include=None, fail='soft',
                 **kwargs):

        data = {}

        for key, l in (('mx', mx), ('a', a), ('include', include)):
            if l is True:
                data[key] = key + ' '
            elif l:
                data[key] = ' '.join('%s:%s' % (key, el) for el in l) + ' '
            else:
                data[key] = ''

        if fail == 'soft':
            data['fail'] = '~all'
        elif fail == 'hard':
            data['fail'] = '-all'
        else:
            raise ValueError("unknown failure type")

        data = 'v=spf1 %(a)s%(mx)s%(include)s%(fail)s' % data
        TXT.__init__(self, host, data, **kwargs)
