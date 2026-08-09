from types import SimpleNamespace

from app.services.discovery_collectors import DHCPLeaseCorrelationCollector

def test_dhcp_description_reservation_and_lease_are_parsed_as_read_only_evidence():
    row=SimpleNamespace(ip_address="10.0.0.5",mac_address="FE:6D:77:24:38:2B",hostname="HR-LT-01",source="Windows DHCP export",lease_server="dhcp01",starts_at="start",expires_at="end",is_reservation=True,reservation_name="HR laptop",description="HR Training Laptop 1")
    db=SimpleNamespace(scalar=lambda _query:row)
    result=DHCPLeaseCorrelationCollector(db).collect(row.ip_address)
    assert result.data["description"] == "HR Training Laptop 1"
    assert result.data["description_source"] == "DHCP"
    assert result.data["dhcp_lease"]["is_reservation"] is True
    assert any(item["evidence_type"] == "description" and item["source"] == "dhcp" for item in result.evidence)

def test_dhcp_unavailable_is_optional():
    db=SimpleNamespace(scalar=lambda _query:None)
    result=DHCPLeaseCorrelationCollector(db).collect("10.0.0.6")
    assert result.hostnames == [] and result.evidence == [] and result.data == {}
