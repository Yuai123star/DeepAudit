import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Mock } from "vitest";

// Mock serverClient before importing prompts
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
	getPromptTemplates,
	getPromptTemplate,
	createPromptTemplate,
	updatePromptTemplate,
	deletePromptTemplate,
	testPromptTemplate,
	setDefaultPromptTemplate,
} from "../prompts";

describe("prompts API", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	// ---- getPromptTemplates ----
	describe("getPromptTemplates", () => {
		it("should GET /prompts with query params and return template list", async () => {
			const mockResponse = {
				items: [
					{ id: "tmpl-1", name: "SQL Injection", template_type: "analysis" },
					{ id: "tmpl-2", name: "XSS Detection", template_type: "analysis" },
				],
				total: 2,
			};
			(apiClient.get as Mock).mockResolvedValue({ data: mockResponse });

			const result = await getPromptTemplates({
				skip: 0,
				limit: 10,
				template_type: "analysis",
				is_active: true,
			});

			expect(apiClient.get).toHaveBeenCalledTimes(1);
			const [url, options] = (apiClient.get as Mock).mock.calls[0];
			expect(url).toMatch(/^\/prompts\?/);
			expect(url).toContain("skip=0");
			expect(url).toContain("limit=10");
			expect(url).toContain("template_type=analysis");
			expect(url).toContain("is_active=true");
			expect(result).toEqual(mockResponse);
		});

		it("should GET /prompts without query string when no params provided", async () => {
			(apiClient.get as Mock).mockResolvedValue({ data: { items: [], total: 0 } });

			const result = await getPromptTemplates();

			expect(apiClient.get).toHaveBeenCalledWith("/prompts");
			expect(result).toEqual({ items: [], total: 0 });
		});
	});

	// ---- getPromptTemplate ----
	describe("getPromptTemplate", () => {
		it("should GET /prompts/:id and return a single template", async () => {
			const mockTemplate = {
				id: "tmpl-1",
				name: "SQL Injection",
				template_type: "analysis",
				content_zh: "检测SQL注入",
				content_en: "Detect SQL injection",
			};
			(apiClient.get as Mock).mockResolvedValue({ data: mockTemplate });

			const result = await getPromptTemplate("tmpl-1");

			expect(apiClient.get).toHaveBeenCalledWith("/prompts/tmpl-1");
			expect(result).toEqual(mockTemplate);
		});

		it("should propagate errors for non-existent template", async () => {
			(apiClient.get as Mock).mockRejectedValue(new Error("Not found"));

			await expect(getPromptTemplate("nonexistent")).rejects.toThrow("Not found");
		});
	});

	// ---- createPromptTemplate ----
	describe("createPromptTemplate", () => {
		it("should POST to /prompts with template data", async () => {
			const createData = {
				name: "New Template",
				template_type: "analysis",
				content_zh: "中文内容",
			};
			const mockResponse = { id: "tmpl-new", ...createData };
			(apiClient.post as Mock).mockResolvedValue({ data: mockResponse });

			const result = await createPromptTemplate(createData);

			expect(apiClient.post).toHaveBeenCalledWith("/prompts", createData);
			expect(result).toEqual(mockResponse);
		});

		it("should propagate errors on creation failure", async () => {
			(apiClient.post as Mock).mockRejectedValue(new Error("Validation error"));

			await expect(
				createPromptTemplate({ name: "Bad Template" }),
			).rejects.toThrow("Validation error");
		});
	});

	// ---- updatePromptTemplate ----
	describe("updatePromptTemplate", () => {
		it("should PUT to /prompts/:id with update data", async () => {
			const updateData = { name: "Updated Template", is_active: false };
			const mockResponse = { id: "tmpl-1", ...updateData };
			(apiClient.put as Mock).mockResolvedValue({ data: mockResponse });

			const result = await updatePromptTemplate("tmpl-1", updateData);

			expect(apiClient.put).toHaveBeenCalledWith("/prompts/tmpl-1", updateData);
			expect(result).toEqual(mockResponse);
		});
	});

	// ---- deletePromptTemplate ----
	describe("deletePromptTemplate", () => {
		it("should DELETE /prompts/:id", async () => {
			(apiClient.delete as Mock).mockResolvedValue({ data: null });

			await deletePromptTemplate("tmpl-1");

			expect(apiClient.delete).toHaveBeenCalledWith("/prompts/tmpl-1");
		});

		it("should propagate errors on delete failure", async () => {
			(apiClient.delete as Mock).mockRejectedValue(new Error("Forbidden"));

			await expect(deletePromptTemplate("tmpl-1")).rejects.toThrow("Forbidden");
		});
	});

	// ---- testPromptTemplate ----
	describe("testPromptTemplate", () => {
		it("should POST to /prompts/test with test data", async () => {
			const testData = {
				content: "Analyze this code for SQL injection",
				language: "python",
				code: "query = f'SELECT * FROM users WHERE id = {user_id}'",
				output_language: "zh",
			};
			const mockResponse = {
				success: true,
				result: { vulnerabilities: ["SQL Injection"] },
				execution_time: 1500,
			};
			(apiClient.post as Mock).mockResolvedValue({ data: mockResponse });

			const result = await testPromptTemplate(testData);

			expect(apiClient.post).toHaveBeenCalledWith("/prompts/test", testData);
			expect(result).toEqual(mockResponse);
			expect(result.success).toBe(true);
		});

		it("should handle test failure response", async () => {
			const testData = {
				content: "Test prompt",
				language: "python",
				code: "print('hello')",
			};
			const mockResponse = {
				success: false,
				error: "LLM service unavailable",
			};
			(apiClient.post as Mock).mockResolvedValue({ data: mockResponse });

			const result = await testPromptTemplate(testData);

			expect(result.success).toBe(false);
			expect(result.error).toBe("LLM service unavailable");
		});
	});

	// ---- setDefaultPromptTemplate ----
	describe("setDefaultPromptTemplate", () => {
		it("should POST to /prompts/:id/set-default", async () => {
			(apiClient.post as Mock).mockResolvedValue({ data: null });

			await setDefaultPromptTemplate("tmpl-1");

			expect(apiClient.post).toHaveBeenCalledWith("/prompts/tmpl-1/set-default");
		});

		it("should propagate errors on set-default failure", async () => {
			(apiClient.post as Mock).mockRejectedValue(new Error("Server error"));

			await expect(setDefaultPromptTemplate("tmpl-1")).rejects.toThrow("Server error");
		});
	});
});
