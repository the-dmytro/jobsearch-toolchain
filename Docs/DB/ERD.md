# JobTracker DB Relations (ERD)

```mermaid
erDiagram
    providers ||--o{ opportunities : provider_id
    organizations ||--o{ opportunities : organization_id

    providers ||--o{ automation_runs : provider_id
    artifacts ||--o{ automation_runs : report_artifact_id

    providers ||--o{ source_items : provider_id
    opportunities ||--o{ source_items : opportunity_id
    automation_runs ||--o{ source_items : automation_run_id
    artifacts ||--o{ source_items : artifact_id

    opportunities ||--o{ evaluations : opportunity_id
    automation_runs ||--o{ evaluations : automation_run_id
    providers ||--o{ evaluations : provider_id

    opportunities ||--o{ applications : opportunity_id
    organizations ||--o{ applications : organization_id
    providers ||--o{ applications : provider_id

    applications ||--o{ application_events : application_id

    organizations ||--o{ contacts : organization_id

    applications ||--o{ interviews : application_id
    organizations ||--o{ interviews : organization_id
    artifacts ||--o{ interviews : transcript_artifact_id

    interviews ||--o{ interview_contacts : interview_id
    contacts ||--o{ interview_contacts : contact_id

    applications ||--o{ communications : application_id
    organizations ||--o{ communications : organization_id
    contacts ||--o{ communications : contact_id
    artifacts ||--o{ communications : artifact_id

    providers ||--o{ legacy_import_rows : provider_id
    organizations ||--o{ legacy_import_rows : organization_id
    opportunities ||--o{ legacy_import_rows : opportunity_id
    applications ||--o{ legacy_import_rows : application_id
    source_items ||--o{ legacy_import_rows : source_item_id

    artifacts ||--o{ document_chunks : artifact_id
```



## Notes

- Tables `artifacts` and `insights` use polymorphic links via `(related_type, related_id)` and therefore have no FK constraints for those fields.
- `jobtracker_schema_migrations` is operational metadata and intentionally isolated from domain tables.

