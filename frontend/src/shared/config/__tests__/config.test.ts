import { describe, it, expect } from "vitest";

// Mock the API database module to avoid pulling in axios and complex dependencies
vi.mock("@/shared/api/database", () => ({
	api: {
		projects: {},
		tasks: {},
	},
}));

describe("shared/config and constants", () => {
	describe("env config", () => {
		it("should export env with expected keys", async () => {
			const { env } = await import("@/shared/config/env");
			expect(env).toHaveProperty("APP_ID");
			expect(env).toHaveProperty("API_BASE_URL");
			expect(env).toHaveProperty("isDev");
			expect(env).toHaveProperty("isProd");
		});

		it("should have string APP_ID and API_BASE_URL", async () => {
			const { env } = await import("@/shared/config/env");
			expect(typeof env.APP_ID).toBe("string");
			expect(typeof env.API_BASE_URL).toBe("string");
		});

		it("should have boolean isDev and isProd", async () => {
			const { env } = await import("@/shared/config/env");
			expect(typeof env.isDev).toBe("boolean");
			expect(typeof env.isProd).toBe("boolean");
		});

		it("should use default values when env vars are not set", async () => {
			const { env } = await import("@/shared/config/env");
			// Defaults: APP_ID = "deepaudit", API_BASE_URL = "/api/v1"
			expect(env.APP_ID).toBe("deepaudit");
			expect(env.API_BASE_URL).toBe("/api/v1");
		});
	});

	describe("database config", () => {
		it("should export dbMode as 'api'", async () => {
			const { dbMode } = await import("@/shared/config/database");
			expect(dbMode).toBe("api");
		});

		it("should export isDemoMode as false", async () => {
			const { isDemoMode } = await import("@/shared/config/database");
			expect(isDemoMode).toBe(false);
		});

		it("should export isLocalMode as false", async () => {
			const { isLocalMode } = await import("@/shared/config/database");
			expect(isLocalMode).toBe(false);
		});

		it("should export supabase as null", async () => {
			const { supabase } = await import("@/shared/config/database");
			expect(supabase).toBeNull();
		});

		it("should export api from the mocked database module", async () => {
			const { api } = await import("@/shared/config/database");
			expect(api).toBeDefined();
		});
	});

	describe("constants", () => {
		it("should export SUPPORTED_LANGUAGES with expected languages", async () => {
			const { SUPPORTED_LANGUAGES } = await import(
				"@/shared/constants/index"
			);
			expect(Array.isArray(SUPPORTED_LANGUAGES)).toBe(true);
			expect(SUPPORTED_LANGUAGES).toContain("javascript");
			expect(SUPPORTED_LANGUAGES).toContain("typescript");
			expect(SUPPORTED_LANGUAGES).toContain("python");
			expect(SUPPORTED_LANGUAGES).toContain("java");
		});

		it("should export ISSUE_TYPES with expected types", async () => {
			const { ISSUE_TYPES } = await import("@/shared/constants/index");
			expect(ISSUE_TYPES.BUG).toBe("bug");
			expect(ISSUE_TYPES.SECURITY).toBe("security");
			expect(ISSUE_TYPES.PERFORMANCE).toBe("performance");
			expect(ISSUE_TYPES.STYLE).toBe("style");
			expect(ISSUE_TYPES.MAINTAINABILITY).toBe("maintainability");
		});

		it("should export SEVERITY_LEVELS with all levels", async () => {
			const { SEVERITY_LEVELS } = await import("@/shared/constants/index");
			expect(SEVERITY_LEVELS.CRITICAL).toBe("critical");
			expect(SEVERITY_LEVELS.HIGH).toBe("high");
			expect(SEVERITY_LEVELS.MEDIUM).toBe("medium");
			expect(SEVERITY_LEVELS.LOW).toBe("low");
		});

		it("should export TASK_STATUS with expected statuses", async () => {
			const { TASK_STATUS } = await import("@/shared/constants/index");
			expect(TASK_STATUS.PENDING).toBe("pending");
			expect(TASK_STATUS.RUNNING).toBe("running");
			expect(TASK_STATUS.COMPLETED).toBe("completed");
			expect(TASK_STATUS.FAILED).toBe("failed");
			expect(TASK_STATUS.CANCELLED).toBe("cancelled");
		});

		it("should export DEFAULT_CONFIG with valid values", async () => {
			const { DEFAULT_CONFIG } = await import("@/shared/constants/index");
			expect(DEFAULT_CONFIG.MAX_FILE_SIZE).toBe(200 * 1024);
			expect(DEFAULT_CONFIG.MAX_FILES_PER_SCAN).toBe(0);
			expect(DEFAULT_CONFIG.ANALYSIS_TIMEOUT).toBe(30000);
			expect(DEFAULT_CONFIG.DEBOUNCE_DELAY).toBe(300);
		});

		it("should export STORAGE_KEYS with expected keys", async () => {
			const { STORAGE_KEYS } = await import("@/shared/constants/index");
			expect(STORAGE_KEYS.THEME).toBe("deepaudit-theme");
			expect(STORAGE_KEYS.USER_PREFERENCES).toBe(
				"deepaudit-preferences",
			);
			expect(STORAGE_KEYS.RECENT_PROJECTS).toBe(
				"deepaudit-recent-projects",
			);
		});

		it("should export PROJECT_SOURCE_TYPES as an array (re-exported from projectTypes)", async () => {
			const { PROJECT_SOURCE_TYPES } = await import(
				"@/shared/constants/index"
			);
			// projectTypes.ts exports PROJECT_SOURCE_TYPES as an array (overrides index.ts object)
			expect(Array.isArray(PROJECT_SOURCE_TYPES)).toBe(true);
			expect(PROJECT_SOURCE_TYPES).toHaveLength(2);
			expect(PROJECT_SOURCE_TYPES[0].value).toBe("repository");
			expect(PROJECT_SOURCE_TYPES[1].value).toBe("zip");
		});
	});

	describe("projectTypes", () => {
		it("should export REPOSITORY_PLATFORM_LABELS for all platforms", async () => {
			const { REPOSITORY_PLATFORM_LABELS } = await import(
				"@/shared/constants/projectTypes"
			);
			expect(REPOSITORY_PLATFORM_LABELS.github).toBe("GitHub");
			expect(REPOSITORY_PLATFORM_LABELS.gitlab).toBe("GitLab");
			expect(REPOSITORY_PLATFORM_LABELS.gitea).toBe("Gitea");
			expect(REPOSITORY_PLATFORM_LABELS.other).toBe("\u5176\u4ED6");
		});

		it("should export SOURCE_TYPE_COLORS with bg, text, and border for each type", async () => {
			const { SOURCE_TYPE_COLORS } = await import(
				"@/shared/constants/projectTypes"
			);
			for (const key of ["repository", "zip"] as const) {
				expect(SOURCE_TYPE_COLORS[key]).toHaveProperty("bg");
				expect(SOURCE_TYPE_COLORS[key]).toHaveProperty("text");
				expect(SOURCE_TYPE_COLORS[key]).toHaveProperty("border");
			}
		});

		it("should export PLATFORM_COLORS with bg and text for each platform", async () => {
			const { PLATFORM_COLORS } = await import(
				"@/shared/constants/projectTypes"
			);
			for (const key of ["github", "gitlab", "gitea", "other"] as const) {
				expect(PLATFORM_COLORS[key]).toHaveProperty("bg");
				expect(PLATFORM_COLORS[key]).toHaveProperty("text");
			}
		});

		it("should export PROJECT_SOURCE_TYPES as an array with two options", async () => {
			const mod = await import("@/shared/constants/projectTypes");
			const types = mod.PROJECT_SOURCE_TYPES;
			expect(Array.isArray(types)).toBe(true);
			expect(types).toHaveLength(2);
			expect(types[0].value).toBe("repository");
			expect(types[1].value).toBe("zip");
			// Each option has label and description
			for (const item of types) {
				expect(item).toHaveProperty("label");
				expect(item).toHaveProperty("description");
			}
		});

		it("should export REPOSITORY_PLATFORMS derived from REPOSITORY_PLATFORM_LABELS", async () => {
			const { REPOSITORY_PLATFORMS, REPOSITORY_PLATFORM_LABELS } =
				await import("@/shared/constants/projectTypes");
			expect(REPOSITORY_PLATFORMS).toHaveLength(
				Object.keys(REPOSITORY_PLATFORM_LABELS).length,
			);
			for (const platform of REPOSITORY_PLATFORMS) {
				expect(platform).toHaveProperty("value");
				expect(platform).toHaveProperty("label");
			}
		});
	});
});
