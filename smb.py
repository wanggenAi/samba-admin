import ldap3

host = "127.0.0.1"
user = "Administrator@EVMS.BSTU.EDU"
password = input()
base_dn = "DC=evms,DC=bstu,DC=edu"

server = ldap3.Server(host, get_info="ALL")
conn = ldap3.Connection(server, user=user, password=password, auto_bind=True)

conn.search(base_dn, "(objectClass=*)", attributes=ldap3.ALL_ATTRIBUTES)
print(conn.result)
print(conn.entries)