export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export interface Database {
  public: {
    Tables: {
      crm_owner_allowlist: {
        Row: { email: string };
        Insert: { email: string };
        Update: { email?: string };
        Relationships: [];
      };
      providers: {
        Row: {
          id: string;
          slug: string;
          name: string;
          provider_type: string;
          website_url: string | null;
          notes: string | null;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          slug: string;
          name: string;
          provider_type?: string;
          website_url?: string | null;
          notes?: string | null;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["providers"]["Insert"]>;
        Relationships: [];
      };
      organizations: {
        Row: {
          id: string;
          name: string;
          normalized_name: string;
          website_url: string | null;
          domains: string[];
          industry: string | null;
          location_text: string | null;
          notes: string | null;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          name: string;
          normalized_name: string;
          website_url?: string | null;
          domains?: string[];
          industry?: string | null;
          location_text?: string | null;
          notes?: string | null;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["organizations"]["Insert"]>;
        Relationships: [];
      };
      opportunities: {
        Row: {
          id: string;
          provider_id: string | null;
          organization_id: string | null;
          opportunity_type: string;
          title: string;
          normalized_title: string | null;
          external_id: string | null;
          source_url: string | null;
          apply_url: string | null;
          location_text: string | null;
          work_model: string | null;
          engagement_type: string | null;
          seniority: string | null;
          domain: string | null;
          compensation_text: string | null;
          compensation_min: number | null;
          compensation_max: number | null;
          compensation_currency: string | null;
          budget_type: string | null;
          source_status: string | null;
          first_seen_at: string | null;
          last_seen_at: string | null;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          provider_id?: string | null;
          organization_id?: string | null;
          opportunity_type?: string;
          title: string;
          normalized_title?: string | null;
          external_id?: string | null;
          source_url?: string | null;
          apply_url?: string | null;
          location_text?: string | null;
          work_model?: string | null;
          engagement_type?: string | null;
          seniority?: string | null;
          domain?: string | null;
          compensation_text?: string | null;
          compensation_min?: number | null;
          compensation_max?: number | null;
          compensation_currency?: string | null;
          budget_type?: string | null;
          source_status?: string | null;
          first_seen_at?: string | null;
          last_seen_at?: string | null;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["opportunities"]["Insert"]>;
        Relationships: [];
      };
      artifacts: {
        Row: {
          id: string;
          artifact_type: string;
          title: string | null;
          storage_bucket: string | null;
          storage_path: string | null;
          local_path: string | null;
          mime_type: string | null;
          sha256: string | null;
          size_bytes: number | null;
          related_type: string | null;
          related_id: string | null;
          metadata: Json;
          created_at: string;
        };
        Insert: {
          id?: string;
          artifact_type: string;
          title?: string | null;
          storage_bucket?: string | null;
          storage_path?: string | null;
          local_path?: string | null;
          mime_type?: string | null;
          sha256?: string | null;
          size_bytes?: number | null;
          related_type?: string | null;
          related_id?: string | null;
          metadata?: Json;
          created_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["artifacts"]["Insert"]>;
        Relationships: [];
      };
      automation_runs: {
        Row: {
          id: string;
          provider_id: string | null;
          run_key: string | null;
          started_at: string | null;
          finished_at: string | null;
          status: string;
          report_artifact_id: string | null;
          report_email_sent: boolean | null;
          report_email_subject: string | null;
          source_items_count: number;
          opportunities_count: number;
          evaluations_count: number;
          manual_review_count: number;
          summary: string | null;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          provider_id?: string | null;
          run_key?: string | null;
          started_at?: string | null;
          finished_at?: string | null;
          status?: string;
          report_artifact_id?: string | null;
          report_email_sent?: boolean | null;
          report_email_subject?: string | null;
          source_items_count?: number;
          opportunities_count?: number;
          evaluations_count?: number;
          manual_review_count?: number;
          summary?: string | null;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["automation_runs"]["Insert"]>;
        Relationships: [];
      };
      source_items: {
        Row: {
          id: string;
          provider_id: string | null;
          opportunity_id: string | null;
          automation_run_id: string | null;
          artifact_id: string | null;
          source_type: string;
          external_id: string | null;
          source_url: string | null;
          source_timestamp: string | null;
          title: string | null;
          summary: string | null;
          raw_text: string | null;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          provider_id?: string | null;
          opportunity_id?: string | null;
          automation_run_id?: string | null;
          artifact_id?: string | null;
          source_type: string;
          external_id?: string | null;
          source_url?: string | null;
          source_timestamp?: string | null;
          title?: string | null;
          summary?: string | null;
          raw_text?: string | null;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["source_items"]["Insert"]>;
        Relationships: [];
      };
      evaluations: {
        Row: {
          id: string;
          opportunity_id: string;
          automation_run_id: string | null;
          provider_id: string | null;
          score: number | null;
          confidence: string | null;
          recommendation: string | null;
          priority: string | null;
          verdict: string | null;
          main_match: string | null;
          main_risks: string | null;
          missing_information: string | null;
          positioning_angle: string | null;
          salary_expectation: string | null;
          pricing_recommendation: string | null;
          proposal_text: string | null;
          action_next: string | null;
          manual_review_reason: string | null;
          evaluated_at: string;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          opportunity_id: string;
          automation_run_id?: string | null;
          provider_id?: string | null;
          score?: number | null;
          confidence?: string | null;
          recommendation?: string | null;
          priority?: string | null;
          verdict?: string | null;
          main_match?: string | null;
          main_risks?: string | null;
          missing_information?: string | null;
          positioning_angle?: string | null;
          salary_expectation?: string | null;
          pricing_recommendation?: string | null;
          proposal_text?: string | null;
          action_next?: string | null;
          manual_review_reason?: string | null;
          evaluated_at?: string;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["evaluations"]["Insert"]>;
        Relationships: [];
      };
      applications: {
        Row: {
          id: string;
          opportunity_id: string | null;
          organization_id: string | null;
          provider_id: string | null;
          application_channel: string | null;
          status: string;
          current_stage: string | null;
          applied_at: string | null;
          salary_requested_text: string | null;
          salary_requested_min: number | null;
          salary_requested_max: number | null;
          salary_requested_currency: string | null;
          outcome: string | null;
          decline_reason: string | null;
          passed: boolean | null;
          notes: string | null;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          opportunity_id?: string | null;
          organization_id?: string | null;
          provider_id?: string | null;
          application_channel?: string | null;
          status?: string;
          current_stage?: string | null;
          applied_at?: string | null;
          salary_requested_text?: string | null;
          salary_requested_min?: number | null;
          salary_requested_max?: number | null;
          salary_requested_currency?: string | null;
          outcome?: string | null;
          decline_reason?: string | null;
          passed?: boolean | null;
          notes?: string | null;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["applications"]["Insert"]>;
        Relationships: [];
      };
      application_events: {
        Row: {
          id: string;
          application_id: string;
          event_type: string;
          event_at: string | null;
          title: string | null;
          description: string | null;
          metadata: Json;
          created_at: string;
        };
        Insert: {
          id?: string;
          application_id: string;
          event_type: string;
          event_at?: string | null;
          title?: string | null;
          description?: string | null;
          metadata?: Json;
          created_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["application_events"]["Insert"]>;
        Relationships: [];
      };
      contacts: {
        Row: {
          id: string;
          organization_id: string | null;
          full_name: string | null;
          role_title: string | null;
          email: string | null;
          linkedin_url: string | null;
          notes: string | null;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          organization_id?: string | null;
          full_name?: string | null;
          role_title?: string | null;
          email?: string | null;
          linkedin_url?: string | null;
          notes?: string | null;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["contacts"]["Insert"]>;
        Relationships: [];
      };
      interviews: {
        Row: {
          id: string;
          application_id: string;
          organization_id: string | null;
          stage: string | null;
          scheduled_at: string | null;
          completed_at: string | null;
          meeting_url: string | null;
          result: string | null;
          feedback_summary: string | null;
          transcript_artifact_id: string | null;
          notes: string | null;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          application_id: string;
          organization_id?: string | null;
          stage?: string | null;
          scheduled_at?: string | null;
          completed_at?: string | null;
          meeting_url?: string | null;
          result?: string | null;
          feedback_summary?: string | null;
          transcript_artifact_id?: string | null;
          notes?: string | null;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["interviews"]["Insert"]>;
        Relationships: [];
      };
      interview_contacts: {
        Row: {
          interview_id: string;
          contact_id: string;
          role_in_interview: string | null;
        };
        Insert: {
          interview_id: string;
          contact_id: string;
          role_in_interview?: string | null;
        };
        Update: Partial<Database["public"]["Tables"]["interview_contacts"]["Insert"]>;
        Relationships: [];
      };
      communications: {
        Row: {
          id: string;
          application_id: string | null;
          organization_id: string | null;
          contact_id: string | null;
          artifact_id: string | null;
          direction: string | null;
          channel: string | null;
          subject: string | null;
          sent_at: string | null;
          summary: string | null;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          application_id?: string | null;
          organization_id?: string | null;
          contact_id?: string | null;
          artifact_id?: string | null;
          direction?: string | null;
          channel?: string | null;
          subject?: string | null;
          sent_at?: string | null;
          summary?: string | null;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["communications"]["Insert"]>;
        Relationships: [];
      };
      insights: {
        Row: {
          id: string;
          insight_type: string;
          title: string;
          body: string | null;
          related_type: string | null;
          related_id: string | null;
          confidence: string | null;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          insight_type: string;
          title: string;
          body?: string | null;
          related_type?: string | null;
          related_id?: string | null;
          confidence?: string | null;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["insights"]["Insert"]>;
        Relationships: [];
      };
      legacy_import_rows: {
        Row: {
          id: string;
          source_file: string;
          row_number: number;
          stable_key: string;
          fallback_key: string;
          raw_row: Json;
          original_link_text: string | null;
          provider_id: string | null;
          organization_id: string | null;
          opportunity_id: string | null;
          application_id: string | null;
          source_item_id: string | null;
          import_warnings: string[];
          created_at: string;
          updated_at: string;
        };
        Insert: Record<string, never>;
        Update: Record<string, never>;
        Relationships: [];
      };
      email_notifications: {
        Row: {
          id: string;
          provider_id: string | null;
          automation_run_id: string | null;
          idempotency_key: string;
          to_address: string;
          subject: string;
          status: string;
          attempts: number;
          sent_at: string | null;
          last_error: string | null;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          provider_id?: string | null;
          automation_run_id?: string | null;
          idempotency_key: string;
          to_address: string;
          subject: string;
          status?: string;
          attempts?: number;
          sent_at?: string | null;
          last_error?: string | null;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["email_notifications"]["Insert"]>;
        Relationships: [];
      };
      automation_run_events: {
        Row: {
          id: string;
          provider_id: string | null;
          automation_run_id: string | null;
          run_key: string | null;
          event_type: string;
          severity: string;
          message: string | null;
          metadata: Json;
          created_at: string;
        };
        Insert: {
          id?: string;
          provider_id?: string | null;
          automation_run_id?: string | null;
          run_key?: string | null;
          event_type: string;
          severity?: string;
          message?: string | null;
          metadata?: Json;
          created_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["automation_run_events"]["Insert"]>;
        Relationships: [];
      };
      document_chunks: {
        Row: {
          id: string;
          artifact_id: string;
          related_type: string | null;
          related_id: string | null;
          chunk_index: number;
          content: string;
          metadata: Json;
          created_at: string;
        };
        Insert: {
          id?: string;
          artifact_id: string;
          related_type?: string | null;
          related_id?: string | null;
          chunk_index?: number;
          content: string;
          metadata?: Json;
          created_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["document_chunks"]["Insert"]>;
        Relationships: [];
      };
    };
    Views: {
      v_funnel_summary: {
        Row: {
          opportunities_count: number;
          evaluated_count: number;
          applied_count: number;
          interviewing_count: number;
          offer_count: number;
          opp_to_eval_pct: number;
          eval_to_applied_pct: number;
          applied_to_interview_pct: number;
          interview_to_offer_pct: number;
        };
        Relationships: [];
      };
      v_weekly_activity: {
        Row: {
          week_start: string;
          opportunities: number;
          applications: number;
          interviews: number;
        };
        Relationships: [];
      };
      v_response_latency: {
        Row: {
          application_id: string;
          applied_at: string;
          first_response_at: string;
          latency_days: number;
        };
        Relationships: [];
      };
      v_source_effectiveness: {
        Row: {
          provider_id: string;
          provider_slug: string;
          provider_name: string;
          opportunities: number;
          applications: number;
          interviews: number;
          offers: number;
          app_to_interview_pct: number;
        };
        Relationships: [];
      };
      v_pipeline_aging: {
        Row: {
          application_id: string;
          organization_name: string;
          opportunity_title: string;
          current_stage: string | null;
          status: string;
          days_in_stage: number;
          applied_at: string | null;
          updated_at: string;
        };
        Relationships: [];
      };
      v_score_outcomes: {
        Row: {
          score_bucket: string;
          evaluation_count: number;
          offer_count: number;
          resolved_count: number;
          avg_score: number | null;
        };
        Relationships: [];
      };
    };
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
}

export type Tables<T extends keyof Database["public"]["Tables"]> =
  Database["public"]["Tables"][T]["Row"];

export type Views<T extends keyof Database["public"]["Views"]> =
  Database["public"]["Views"][T]["Row"];
