import {PublicLayout} from "../components/PublicLayout";
const sections=[
 ["Network discovery","Find reachable technology using bounded, property-scoped discovery. Review evidence before devices enter managed inventory."],
 ["Device intelligence","Correlate DNS, DHCP, SNMP, Active Directory, and observed identity without pretending uncertain evidence is fact."],
 ["Network operations","Understand topology, switch ports, VLAN segmentation, health, alerts, and potential operational impact."],
 ["Asset management","Track ownership, lifecycle, warranties, acquisition, vendors, departments, and locations in one managed record."],
 ["IT service operations","Connect incidents to services and assets, manage recurring problems, govern changes, and preserve operational knowledge."],
 ["Multi-property management","Give hotel groups centralized visibility while users and operational records remain property scoped."],
];
export default function FeaturesPage(){return <PublicLayout><section className="public-page-head"><p className="public-eyebrow">Platform capabilities</p><h1>Understand the technology behind every stay.</h1><p>HIOP connects infrastructure intelligence and hospitality operations in one calm, accountable workspace.</p></section><section className="feature-details">{sections.map(([title,body],i)=><article key={title}><span>{String(i+1).padStart(2,"0")}</span><div><h2>{title}</h2><p>{body}</p></div></article>)}</section></PublicLayout>}
