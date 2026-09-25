CREATE TABLE IF NOT EXISTS tenant_domain_map (
    domain     TEXT PRIMARY KEY,
    tenant_id  TEXT NOT NULL
);

INSERT INTO tenant_domain_map (domain, tenant_id) VALUES
    ('bcbs-example.com', 'tenant_bcbs'),
    ('acme.com', 'tenant_employer')
ON CONFLICT (domain) DO NOTHING;
