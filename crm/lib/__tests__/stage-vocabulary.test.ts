import { describe, expect, it } from "vitest";

import {
  classifyApplication,
  eventEvidence,
  interviewStage,
  normalizeStage,
  readStage,
  resetUnknownStageValues,
  statusAndOutcomeForStage,
  unknownStageValues,
} from "@/lib/stages";

/*
 * Values as they occur in the production database (snapshot of 2026-11-25). Every one must be
 * recognised: none may fall into "unknown".
 */

const CURRENT_STAGE_VALUES = [
  "Applied", "Rejected", "Declined", "submitted", "Interview", "Application update",
  "Technical interview", "Phone screen", "AI interview invited, not taken", "Role closed",
  "Technical assessment", "Interview cancelled", "Re-applied", "Follow-up sent", "Offer meeting",
  "Offer declined", "Reapplication timing", "Rejected after screen", "Technical challenge feedback",
  "Waiting for feedback", "Role filled", "Video interview cancelled by employer; awaiting update",
  "Role discussion", "Intro call", "First interview", "application_review", "Role on hold",
  "Technical interview follow-up", "Exercise passed but role filled", "Interview scheduled",
  "Rejected after first stage",
];

const STATUS_VALUES = [
  "applied", "declined", "Applied", "interviewing", "Rejected", "Declined", "Re-applied",
  "Offer declined", "follow_up", "offer",
];

const OUTCOME_VALUES = [
  "declined", "Applied", "Rejected", "Declined", "Re-applied", "Offer declined", "offer",
];

const EVENT_TYPES = [
  "applied", "interview_scheduled", "application_received", "rejected", "application_update",
  "declined", "follow_up", "interview_cancelled", "assessment_invited", "role_closed",
  "interview_completed", "recruiter_contact", "opportunity_shared", "candidate_reply",
  "info_request", "offer_meeting", "future_consideration", "gdpr", "client_submission",
  "rejection_received", "offer",
];

const INTERVIEW_STAGES = [
  "Interview", "Phone screen", "Technical interview", "Intro call", "Recruiter screen",
  "Live coding", "Take-home exercise", "Final interview loop", "Offer meeting",
];

describe("real vocabulary: free-text stages", () => {
  it.each(CURRENT_STAGE_VALUES)("recognises current_stage %j", (value) => {
    expect(readStage(value).recognised).toBe(true);
  });

  it.each(STATUS_VALUES)("recognises status %j", (value) => {
    expect(readStage(value).recognised).toBe(true);
  });

  it.each(OUTCOME_VALUES)("recognises outcome %j", (value) => {
    expect(readStage(value).recognised).toBe(true);
  });

  it.each(INTERVIEW_STAGES)("recognises interview stage %j", (value) => {
    expect(readStage(value).recognised).toBe(true);
    expect(interviewStage(value)).toBeDefined();
  });

  it("never records a listed value as unknown", () => {
    resetUnknownStageValues();
    for (const value of [...CURRENT_STAGE_VALUES, ...STATUS_VALUES, ...OUTCOME_VALUES, ...INTERVIEW_STAGES]) {
      readStage(value);
    }
    expect(unknownStageValues()).toEqual([]);
  });

  it("records a value that no rule recognises, for diagnostics", () => {
    resetUnknownStageValues();
    expect(readStage("negotiating with legal").recognised).toBe(false);
    expect(unknownStageValues()).toEqual(["negotiating with legal"]);
    resetUnknownStageValues();
  });
});

describe("real vocabulary: sensible categories", () => {
  it.each([
    ["Applied", "applied", null],
    ["submitted", "applied", null],
    ["Application update", "applied", null],
    ["application_review", "applied", null],
    ["Follow-up sent", "applied", null],
    ["Waiting for feedback", "applied", null],
    ["Role on hold", "applied", null],
    ["Re-applied", "applied", null],
    ["Reapplication timing", "applied", null],
    ["Phone screen", "screening", null],
    ["Intro call", "screening", null],
    ["Role discussion", "screening", null],
    ["Interview", "tech_interview", null],
    ["Interview scheduled", "tech_interview", null],
    ["Technical interview", "tech_interview", null],
    ["Technical assessment", "tech_interview", null],
    ["Technical challenge feedback", "tech_interview", null],
    ["Technical interview follow-up", "tech_interview", null],
    ["Final interview loop", "onsite", null],
    ["Offer meeting", "offer", null],
    ["Rejected", null, "rejected"],
    ["Declined", null, "rejected"],
    ["Role closed", null, "rejected"],
    ["Role filled", null, "rejected"],
    ["Rejected after screen", "screening", "rejected"],
    ["Rejected after first stage", "screening", "rejected"],
    ["Exercise passed but role filled", "tech_interview", "rejected"],
    ["Offer declined", "offer", "withdrawn"],
    ["AI interview invited, not taken", "tech_interview", "withdrawn"],
    ["Video interview cancelled by employer; awaiting update", "tech_interview", "rejected"],
  ])("%j is stage %s, closed %s", (value, stage, closed) => {
    const reading = readStage(value);
    expect(reading.stage).toBe(stage);
    expect(reading.closed).toBe(closed);
  });

  it("reads a rejected status as closed and a rejected outcome as the employer's rejection", () => {
    expect(classifyApplication({ current_stage: "Rejected after screen", status: "rejected", outcome: "rejected" })).toEqual({
      stage: "screening",
      outcome: "rejected",
      open: false,
    });
  });

  it("lifts an interviewing status to at least screening when the stage is only applied", () => {
    expect(classifyApplication({ current_stage: "Applied", status: "interviewing", outcome: null })).toEqual({
      stage: "screening",
      outcome: "active",
      open: true,
    });
  });

  it("keeps an open offer open, and an offer declined closed as withdrawn", () => {
    expect(classifyApplication({ current_stage: "offer", status: "offer", outcome: null })).toMatchObject({
      outcome: "offer",
      open: true,
    });
    expect(classifyApplication({ current_stage: "Offer declined", status: "applied", outcome: null })).toMatchObject({
      stage: "offer",
      outcome: "withdrawn",
      open: false,
    });
  });

  it("writes status and outcome with each board stage, clearing the rejection when leaving Closed", () => {
    expect(statusAndOutcomeForStage("applied")).toEqual({ status: "applied", outcome: null });
    expect(statusAndOutcomeForStage("screening")).toEqual({ status: "interviewing", outcome: null });
    expect(statusAndOutcomeForStage("tech_interview")).toEqual({ status: "interviewing", outcome: null });
    expect(statusAndOutcomeForStage("onsite")).toEqual({ status: "interviewing", outcome: null });
    expect(statusAndOutcomeForStage("offer")).toEqual({ status: "offer", outcome: null });
    expect(statusAndOutcomeForStage("rejected")).toEqual({ status: "rejected", outcome: "rejected" });
    expect(normalizeStage("Rejected after screen")).toBe("rejected");
  });
});

describe("real vocabulary: event types", () => {
  it.each(EVENT_TYPES)("knows event type %j", (type) => {
    expect(eventEvidence(type).known).toBe(true);
  });

  it("counts interviews, invitations and employer messages as responses, and own actions as none", () => {
    expect(eventEvidence("interview_scheduled").response).toBe(true);
    expect(eventEvidence("assessment_invited").response).toBe(true);
    expect(eventEvidence("recruiter_contact").response).toBe(true);
    expect(eventEvidence("info_request").response).toBe(true);
    expect(eventEvidence("rejected").response).toBe(true);
    expect(eventEvidence("rejection_received").response).toBe(true);
    expect(eventEvidence("role_closed").response).toBe(true);
    expect(eventEvidence("offer").response).toBe(true);

    for (const type of ["applied", "application_received", "follow_up", "candidate_reply", "opportunity_shared", "gdpr", "future_consideration"]) {
      expect(eventEvidence(type).response).toBe(false);
    }
  });

  it("marks employer rejections as closing, and gives stage evidence for interview and offer events", () => {
    expect(eventEvidence("declined").closing).toBe(true);
    expect(eventEvidence("role_closed").closing).toBe(true);
    expect(eventEvidence("interview_scheduled").stage).toBe("tech_interview");
    expect(eventEvidence("recruiter_contact").stage).toBe("screening");
    expect(eventEvidence("offer_meeting").stage).toBe("offer");
  });
});
