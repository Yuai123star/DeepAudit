import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Mock } from "vitest";

// Mock serverClient before importing rules
vi.mock("../serverClient", () => ({
	apiClient: {
		get: vi.fn(),
		post: vi.fn(),
		put: vi.fn(),
		delete: vi.fn(),
		patch: vi.fn(),
	},
}));

import { apiClient } from "../serverClient";
import {
	getRuleSets,
	getRuleSet,
	createRuleSet,
	updateRuleSet,
	deleteRuleSet,
	exportRuleSet,
	importRuleSet,
	addRuleToSet,
	updateRule,
	deleteRule,
	toggleRule,
} from "../rules";

describe("rules API", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	// ---- getRuleSets ----
	describe("getRuleSets", () => {
		it("should GET /rules with query params", async () => {
			const mockResponse = {
				items: [
					{ id: "rs-1", name: "OWASP Top 10", language: "python" },
				],
				total: 1,
			};
			(apiClient.get as Mock).mockResolvedValue({ data: mockResponse });

			const result = await getRuleSets({
				skip: 0,
				limit: 20,
				language: "python",
				is_active: true,
			});

			const [url] = (apiClient.get as Mock).mock.calls[0];
			expect(url).toMatch(/^\/rules\?/);
			expect(url).toContain("skip=0");
			expect(url).toContain("limit=20");
			expect(url).toContain("language=python");
			expect(url).toContain("is_active=true");
			expect(result).toEqual(mockResponse);
		});

		it("should GET /rules without query string when no params provided", async () => {
			(apiClient.get as Mock).mockResolvedValue({ data: { items: [], total: 0 } });

			const result = await getRuleSets();

			expect(apiClient.get).toHaveBeenCalledWith("/rules");
			expect(result).toEqual({ items: [], total: 0 });
		});
	});

	// ---- getRuleSet ----
	describe("getRuleSet", () => {
		it("should GET /rules/:id and return a single rule set", async () => {
			const mockRuleSet = {
				id: "rs-1",
				name: "OWASP Top 10",
				language: "python",
				rules: [],
				rules_count: 0,
				enabled_rules_count: 0,
			};
			(apiClient.get as Mock).mockResolvedValue({ data: mockRuleSet });

			const result = await getRuleSet("rs-1");

			expect(apiClient.get).toHaveBeenCalledWith("/rules/rs-1");
			expect(result).toEqual(mockRuleSet);
		});

		it("should propagate errors for non-existent rule set", async () => {
			(apiClient.get as Mock).mockRejectedValue(new Error("Not found"));

			await expect(getRuleSet("nonexistent")).rejects.toThrow("Not found");
		});
	});

	// ---- createRuleSet ----
	describe("createRuleSet", () => {
		it("should POST to /rules with rule set data", async () => {
			const createData = {
				name: "Custom Rules",
				language: "typescript",
				rule_type: "custom",
				rules: [
					{ rule_code: "RULE-001", name: "XSS Check", category: "security" },
				],
			};
			const mockResponse = { id: "rs-new", ...createData, rules_count: 1 };
			(apiClient.post as Mock).mockResolvedValue({ data: mockResponse });

			const result = await createRuleSet(createData);

			expect(apiClient.post).toHaveBeenCalledWith("/rules", createData);
			expect(result.id).toBe("rs-new");
		});
	});

	// ---- updateRuleSet ----
	describe("updateRuleSet", () => {
		it("should PUT to /rules/:id with update data", async () => {
			const updateData = { name: "Updated Rules", is_active: true };
			const mockResponse = { id: "rs-1", ...updateData };
			(apiClient.put as Mock).mockResolvedValue({ data: mockResponse });

			const result = await updateRuleSet("rs-1", updateData);

			expect(apiClient.put).toHaveBeenCalledWith("/rules/rs-1", updateData);
			expect(result).toEqual(mockResponse);
		});
	});

	// ---- deleteRuleSet ----
	describe("deleteRuleSet", () => {
		it("should DELETE /rules/:id", async () => {
			(apiClient.delete as Mock).mockResolvedValue({ data: null });

			await deleteRuleSet("rs-1");

			expect(apiClient.delete).toHaveBeenCalledWith("/rules/rs-1");
		});

		it("should propagate errors on delete failure", async () => {
			(apiClient.delete as Mock).mockRejectedValue(new Error("Forbidden"));

			await expect(deleteRuleSet("rs-1")).rejects.toThrow("Forbidden");
		});
	});

	// ---- exportRuleSet ----
	describe("exportRuleSet", () => {
		it("should GET /rules/:id/export with blob responseType", async () => {
			const mockBlob = new Blob(["exported rules"], { type: "application/json" });
			(apiClient.get as Mock).mockResolvedValue({ data: mockBlob });

			const result = await exportRuleSet("rs-1");

			expect(apiClient.get).toHaveBeenCalledWith("/rules/rs-1/export", {
				responseType: "blob",
			});
			expect(result).toBe(mockBlob);
		});
	});

	// ---- importRuleSet ----
	describe("importRuleSet", () => {
		it("should POST to /rules/import with import data", async () => {
			const importData = {
				name: "Imported Rules",
				rules: [
					{ rule_code: "IMP-001", name: "Imported Rule", category: "security" },
				],
			};
			const mockResponse = { id: "rs-imp", ...importData, rules_count: 1 };
			(apiClient.post as Mock).mockResolvedValue({ data: mockResponse });

			const result = await importRuleSet(importData);

			expect(apiClient.post).toHaveBeenCalledWith("/rules/import", importData);
			expect(result.id).toBe("rs-imp");
		});
	});

	// ---- addRuleToSet ----
	describe("addRuleToSet", () => {
		it("should POST to /rules/:ruleSetId/rules with rule data", async () => {
			const ruleData = {
				rule_code: "NEW-001",
				name: "Buffer Overflow",
				category: "memory_safety",
				severity: "critical",
			};
			const mockResponse = { id: "rule-new", ...ruleData };
			(apiClient.post as Mock).mockResolvedValue({ data: mockResponse });

			const result = await addRuleToSet("rs-1", ruleData);

			expect(apiClient.post).toHaveBeenCalledWith("/rules/rs-1/rules", ruleData);
			expect(result).toEqual(mockResponse);
		});
	});

	// ---- updateRule ----
	describe("updateRule", () => {
		it("should PUT to /rules/:ruleSetId/rules/:ruleId with update data", async () => {
			const updateData = { name: "Updated Rule", enabled: false };
			const mockResponse = { id: "rule-1", ...updateData };
			(apiClient.put as Mock).mockResolvedValue({ data: mockResponse });

			const result = await updateRule("rs-1", "rule-1", updateData);

			expect(apiClient.put).toHaveBeenCalledWith(
				"/rules/rs-1/rules/rule-1",
				updateData,
			);
			expect(result).toEqual(mockResponse);
		});
	});

	// ---- deleteRule ----
	describe("deleteRule", () => {
		it("should DELETE /rules/:ruleSetId/rules/:ruleId", async () => {
			(apiClient.delete as Mock).mockResolvedValue({ data: null });

			await deleteRule("rs-1", "rule-1");

			expect(apiClient.delete).toHaveBeenCalledWith("/rules/rs-1/rules/rule-1");
		});
	});

	// ---- toggleRule ----
	describe("toggleRule", () => {
		it("should PUT to /rules/:ruleSetId/rules/:ruleId/toggle and return enabled state", async () => {
			const mockResponse = { enabled: true, message: "Rule enabled" };
			(apiClient.put as Mock).mockResolvedValue({ data: mockResponse });

			const result = await toggleRule("rs-1", "rule-1");

			expect(apiClient.put).toHaveBeenCalledWith(
				"/rules/rs-1/rules/rule-1/toggle",
			);
			expect(result).toEqual(mockResponse);
			expect(result.enabled).toBe(true);
		});

		it("should return disabled state on toggle", async () => {
			const mockResponse = { enabled: false, message: "Rule disabled" };
			(apiClient.put as Mock).mockResolvedValue({ data: mockResponse });

			const result = await toggleRule("rs-1", "rule-1");

			expect(result.enabled).toBe(false);
		});
	});
});
