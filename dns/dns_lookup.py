

import ipaddress

import dns.exception
import dns.rdatatype
import dns.resolver
import dns.reversename

TYPE_ORDER = ["CNAME", "A", "AAAA", "MX", "PTR"]


def _record_used(records, ip):
    """Work out which record type was used to get the answer."""
    if any(r["type"] == "CNAME" for r in records):
        return "CNAME"
    if any(r["type"] in ("A", "AAAA") for r in records):
        return "A" if ipaddress.ip_address(ip).version == 4 else "AAAA"
    if any(r["type"] == "PTR" for r in records):
        return "PTR"
    return None


def _result(target, ip=None, hostname=None, records=None, error=None):
    """Build the standard result dictionary."""
    records = records or []
    success = error is None and ip is not None
    return {
        "target": target,
        "ip": ip if success else None,
        "ip_version": ipaddress.ip_address(ip).version if success else None,
        "hostname": hostname,
        "records": records,
        "record_used": _record_used(records, ip) if success else None,
        "cname_chain": [(r["name"], r["value"]) for r in records if r["type"] == "CNAME"],
        "ipv4": [r["value"] for r in records if r["type"] == "A"],
        "ipv6": [r["value"] for r in records if r["type"] == "AAAA"],
        "success": success,
        "status": "SUCCESS" if success else "FAILED",
        "error": error,
    }


def _collect(answer, records):
    """Add every record in a DNS answer (including the CNAME chain) to records."""
    for rrset in answer.response.answer:
        rtype = dns.rdatatype.to_text(rrset.rdtype)
        name = rrset.name.to_text().rstrip(".")
        for rdata in rrset:
            if rtype in ("A", "AAAA"):
                value = rdata.address
            elif rtype in ("CNAME", "PTR"):
                value = rdata.target.to_text().rstrip(".")
            elif rtype == "MX":
                value = f"{rdata.preference} {rdata.exchange.to_text().rstrip('.')}"
            else:
                value = rdata.to_text()
            rec = {"type": rtype, "name": name, "value": value, "ttl": rrset.ttl}
            if not any(r["type"] == rtype and r["name"] == name and r["value"] == value
                       for r in records):
                records.append(rec)


def resolve(target):

    if target is None:
        return _result(target, error="No input given.")
    target = target.strip()
    if not target:
        return _result(target, error="Input is empty. Enter a hostname or IP address.")
    if len(target) > 253:
        return _result(target, error="Hostname is too long (max 253 characters).")
    if " " in target:
        return _result(target, error="Hostname must not contain spaces.")

    # localhost is not in DNS, it comes from the hosts file
    if target.lower() == "localhost":
        rec = {"type": "A", "name": "localhost", "value": "127.0.0.1", "ttl": 0}
        return _result(target, ip="127.0.0.1", hostname="localhost", records=[rec])

    try:
        res = dns.resolver.Resolver()
        res.lifetime = 5.0  # give up after 5 seconds in total
    except dns.exception.DNSException as e:
        return _result(target, error=f"DNS resolver setup failed: {e}")

    records = []

    # 2. Input is already an IP address -> reverse lookup (PTR record)
    try:
        ipaddress.ip_address(target)
        is_ip = True
    except ValueError:
        is_ip = False

    if is_ip:
        hostname = None
        try:
            rev = dns.reversename.from_address(target)
            _collect(res.resolve(rev, "PTR"), records)
            hostname = next((r["value"] for r in records if r["type"] == "PTR"), None)
        except dns.exception.DNSException:
            pass  
        return _result(target, ip=target, hostname=hostname, records=records)


    last_error = None
    for qtype in ("A", "AAAA", "MX"):
        try:
            _collect(res.resolve(target, qtype), records)
        except dns.resolver.NoAnswer:
            continue  
        except dns.resolver.NXDOMAIN:
            return _result(target, error=f"'{target}' does not exist (NXDOMAIN).")
        except dns.resolver.NoNameservers:
            last_error = "No DNS server could answer the query."
        except dns.exception.Timeout:
            last_error = "DNS query timed out."
        except dns.exception.DNSException as e:
            last_error = f"DNS error: {e}"

    records.sort(key=lambda r: TYPE_ORDER.index(r["type"]) if r["type"] in TYPE_ORDER else 99)

    addresses = [r["value"] for r in records if r["type"] in ("A", "AAAA")]
    if not addresses:
        return _result(target, records=records,
                       error=last_error or f"No IP address (A/AAAA) record found for '{target}'.")

    main_ip = next((r["value"] for r in records if r["type"] == "A"), addresses[0])
    return _result(target, ip=main_ip, hostname=target, records=records)


def describe_record_used(r):
    """Return plain-English lines explaining which record was used."""
    used = r["record_used"]
    if not r["success"] or used is None:
        return []
    if used == "CNAME":
        lines = ["Resource record used : CNAME (alias)"]
        for alias, real in r["cname_chain"]:
            lines.append(f"  {alias} is an alias for {real}")
        final = "A" if r["ip_version"] == 4 else "AAAA"
        lines.append(f"  the {final} record of the real name gave the IP")
        return lines
    if used == "PTR":
        return ["Resource record used : PTR (reverse lookup of the IP)"]
    return [f"Resource record used : {used} (direct, not an alias)"]


if __name__ == "__main__":

    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else input("Enter target: ")
    r = resolve(name)
    print("\n[1] DNS RESOLUTION\n")
    print(f"Query    : {r['target']}")
    for rec in r["records"]:
        print(f"{rec['type']:<8} : {rec['name']} -> {rec['value']}   (TTL {rec['ttl']}s)")
    if r["success"]:
        print(f"\nMain IP  : {r['ip']} (IPv{r['ip_version']})")
        print()
        for line in describe_record_used(r):
            print(line)
        print()
    print(f"Status   : {r['status']}")
    if r["error"]:
        print(f"Error    : {r['error']}")
