# Optional CRM and analytics

The Python core and SQLite workflow do not need the CRM. The existing Next.js CRM is optional and requires Node.js 20, hosted Supabase Auth, and the PostgreSQL schema/analytics views.

```bash
cd crm
npm ci
npm test
npm run lint
npm run build
```

Configure the CRM with ignored environment files described in `crm/README.md`. A local Supabase/Docker stack is an advanced testing option, not the standard path.
