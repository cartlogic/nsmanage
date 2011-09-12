from nsmanage import *


domain = Domain(
    A('@', '8.2.2.4', ttl=2400),
    A('foo', '66.123.42.2'),
    CNAME('www', '@', ttl=23200),
    CNAME('blah', 'hello'),
    MX('@', 'mail1.example.com'),
    TXT('@', 'this is a txt record'),
)
