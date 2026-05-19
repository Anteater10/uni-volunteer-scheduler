// frontend/src/lib/architecture/validate.js
//
// Runtime + test-time integrity checks for the architecture graph.
// Throws an Error with all collected issues so the test names stay tight.

import { STATUS } from "../../data/appArchitecture";

const VALID_STATUSES = new Set(Object.values(STATUS));
const VALID_CATEGORIES = new Set([
  "actor",
  "client",
  "api",
  "service",
  "data",
  "external",
]);

export function validateArchitecture({ nodes, flows }) {
  const issues = [];

  // ── nodes ──────────────────────────────────────────────────────────────
  const nodeIds = new Set();
  for (const node of nodes) {
    if (!node.id) issues.push(`node missing id: ${JSON.stringify(node)}`);
    if (nodeIds.has(node.id)) issues.push(`duplicate node id: ${node.id}`);
    nodeIds.add(node.id);

    if (!VALID_STATUSES.has(node.status)) {
      issues.push(`node ${node.id} has invalid status: ${node.status}`);
    }
    if (!VALID_CATEGORIES.has(node.category)) {
      issues.push(`node ${node.id} has invalid category: ${node.category}`);
    }
    if (node.status !== STATUS.WORKING && !node.statusReason) {
      issues.push(
        `node ${node.id} is ${node.status} but has no statusReason`,
      );
    }
    if (typeof node.col !== "number" || typeof node.row !== "number") {
      issues.push(`node ${node.id} missing numeric col/row`);
    }
  }

  // ── flows ──────────────────────────────────────────────────────────────
  const flowIds = new Set();
  for (const flow of flows) {
    if (!flow.id) issues.push(`flow missing id: ${JSON.stringify(flow)}`);
    if (flowIds.has(flow.id)) issues.push(`duplicate flow id: ${flow.id}`);
    flowIds.add(flow.id);

    if (!VALID_STATUSES.has(flow.status)) {
      issues.push(`flow ${flow.id} has invalid status: ${flow.status}`);
    }
    if (flow.status !== STATUS.WORKING && !flow.statusReason) {
      issues.push(
        `flow ${flow.id} is ${flow.status} but has no statusReason`,
      );
    }

    if (!Array.isArray(flow.steps) || flow.steps.length === 0) {
      issues.push(`flow ${flow.id} has no steps`);
      continue;
    }

    const stepNumbers = new Set();
    for (const step of flow.steps) {
      if (typeof step.number !== "number") {
        issues.push(`flow ${flow.id} step missing number`);
      }
      if (stepNumbers.has(step.number)) {
        issues.push(
          `flow ${flow.id} has duplicate step number ${step.number}`,
        );
      }
      stepNumbers.add(step.number);

      if (!nodeIds.has(step.from)) {
        issues.push(
          `flow ${flow.id} step ${step.number}: unknown from-node ${step.from}`,
        );
      }
      if (!nodeIds.has(step.to)) {
        issues.push(
          `flow ${flow.id} step ${step.number}: unknown to-node ${step.to}`,
        );
      }

      if (step.status && !VALID_STATUSES.has(step.status)) {
        issues.push(
          `flow ${flow.id} step ${step.number}: invalid step status ${step.status}`,
        );
      }
      if (
        step.status &&
        step.status !== STATUS.WORKING &&
        !step.statusReason
      ) {
        issues.push(
          `flow ${flow.id} step ${step.number}: ${step.status} step has no statusReason`,
        );
      }
    }
  }

  return issues;
}

export function assertArchitecture(graph) {
  const issues = validateArchitecture(graph);
  if (issues.length) {
    throw new Error(
      `Architecture graph has ${issues.length} integrity issue(s):\n - ${issues.join("\n - ")}`,
    );
  }
}
