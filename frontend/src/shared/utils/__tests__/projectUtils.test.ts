import { describe, it, expect } from "vitest";
import type { Project, ProjectSourceType } from "@/shared/types";
import {
	isRepositoryProject,
	isZipProject,
	getSourceTypeLabel,
	getSourceTypeBadge,
	getRepositoryPlatformLabel,
	canSelectBranch,
	requiresZipUpload,
	getScanMethodDescription,
	validateProjectConfig,
} from "@/shared/utils/projectUtils";

function createMockProject(
	overrides: Partial<Project> = {},
): Project {
	return {
		id: "test-id",
		name: "Test Project",
		source_type: "repository",
		default_branch: "main",
		programming_languages: "typescript",
		owner_id: "owner-1",
		is_active: true,
		created_at: "2025-01-01T00:00:00Z",
		updated_at: "2025-01-01T00:00:00Z",
		...overrides,
	};
}

describe("projectUtils", () => {
	describe("isRepositoryProject", () => {
		it("should return true for repository projects", () => {
			const project = createMockProject({ source_type: "repository" });
			expect(isRepositoryProject(project)).toBe(true);
		});

		it("should return false for zip projects", () => {
			const project = createMockProject({ source_type: "zip" });
			expect(isRepositoryProject(project)).toBe(false);
		});
	});

	describe("isZipProject", () => {
		it("should return true for zip projects", () => {
			const project = createMockProject({ source_type: "zip" });
			expect(isZipProject(project)).toBe(true);
		});

		it("should return false for repository projects", () => {
			const project = createMockProject({ source_type: "repository" });
			expect(isZipProject(project)).toBe(false);
		});
	});

	describe("getSourceTypeLabel", () => {
		it("should return Chinese label for repository", () => {
			expect(getSourceTypeLabel("repository")).toBe("\u8FDC\u7A0B\u4ED3\u5E93");
		});

		it("should return Chinese label for zip", () => {
			expect(getSourceTypeLabel("zip")).toBe("ZIP\u4E0A\u4F20");
		});

		it("should return unknown label for invalid type", () => {
			expect(getSourceTypeLabel("unknown" as ProjectSourceType)).toBe(
				"\u672A\u77E5",
			);
		});
	});

	describe("getSourceTypeBadge", () => {
		it("should return REPO badge for repository", () => {
			expect(getSourceTypeBadge("repository")).toBe("REPO");
		});

		it("should return ZIP badge for zip", () => {
			expect(getSourceTypeBadge("zip")).toBe("ZIP");
		});

		it("should return UNKNOWN badge for invalid type", () => {
			expect(getSourceTypeBadge("other" as ProjectSourceType)).toBe("UNKNOWN");
		});
	});

	describe("getRepositoryPlatformLabel", () => {
		it("should return GitHub for github", () => {
			expect(getRepositoryPlatformLabel("github")).toBe("GitHub");
		});

		it("should return GitLab for gitlab", () => {
			expect(getRepositoryPlatformLabel("gitlab")).toBe("GitLab");
		});

		it("should return Gitea for gitea", () => {
			expect(getRepositoryPlatformLabel("gitea")).toBe("Gitea");
		});

		it("should return fallback for unknown platform", () => {
			expect(getRepositoryPlatformLabel("unknown_platform")).toBe(
				"\u5176\u4ED6",
			);
		});

		it("should return fallback for undefined platform", () => {
			expect(getRepositoryPlatformLabel(undefined)).toBe("\u5176\u4ED6");
		});
	});

	describe("canSelectBranch", () => {
		it("should return true for repository projects with a URL", () => {
			const project = createMockProject({
				source_type: "repository",
				repository_url: "https://github.com/test/repo",
			});
			expect(canSelectBranch(project)).toBe(true);
		});

		it("should return false for repository projects without a URL", () => {
			const project = createMockProject({
				source_type: "repository",
				repository_url: undefined,
			});
			expect(canSelectBranch(project)).toBe(false);
		});

		it("should return false for zip projects even with a URL", () => {
			const project = createMockProject({
				source_type: "zip",
				repository_url: "https://github.com/test/repo",
			});
			expect(canSelectBranch(project)).toBe(false);
		});
	});

	describe("requiresZipUpload", () => {
		it("should return true for zip projects", () => {
			const project = createMockProject({ source_type: "zip" });
			expect(requiresZipUpload(project)).toBe(true);
		});

		it("should return false for repository projects", () => {
			const project = createMockProject({ source_type: "repository" });
			expect(requiresZipUpload(project)).toBe(false);
		});
	});

	describe("getScanMethodDescription", () => {
		it("should describe repository scanning for repository projects", () => {
			const project = createMockProject({
				source_type: "repository",
				repository_type: "github",
			});
			const description = getScanMethodDescription(project);
			expect(description).toContain("GitHub");
			expect(description).toContain("\u4ED3\u5E93");
		});

		it("should describe ZIP upload for zip projects", () => {
			const project = createMockProject({ source_type: "zip" });
			const description = getScanMethodDescription(project);
			expect(description).toContain("ZIP");
		});
	});

	describe("validateProjectConfig", () => {
		it("should return valid for a complete repository project", () => {
			const project = createMockProject({
				name: "My Project",
				source_type: "repository",
				repository_url: "https://github.com/test/repo",
			});
			const result = validateProjectConfig(project);
			expect(result.valid).toBe(true);
			expect(result.errors).toHaveLength(0);
		});

		it("should return valid for a complete zip project", () => {
			const project = createMockProject({
				name: "My Zip Project",
				source_type: "zip",
			});
			const result = validateProjectConfig(project);
			expect(result.valid).toBe(true);
			expect(result.errors).toHaveLength(0);
		});

		it("should return errors when name is empty", () => {
			const project = createMockProject({
				name: "",
				source_type: "zip",
			});
			const result = validateProjectConfig(project);
			expect(result.valid).toBe(false);
			expect(result.errors).toHaveLength(1);
			expect(result.errors[0]).toContain("\u9879\u76EE\u540D\u79F0");
		});

		it("should return errors when name is whitespace only", () => {
			const project = createMockProject({
				name: "   ",
				source_type: "zip",
			});
			const result = validateProjectConfig(project);
			expect(result.valid).toBe(false);
			expect(result.errors).toHaveLength(1);
		});

		it("should return error when repository project has no URL", () => {
			const project = createMockProject({
				name: "Good Name",
				source_type: "repository",
				repository_url: undefined,
			});
			const result = validateProjectConfig(project);
			expect(result.valid).toBe(false);
			expect(result.errors).toHaveLength(1);
			expect(result.errors[0]).toContain("\u4ED3\u5E93\u5730\u5740");
		});

		it("should return multiple errors for a project with empty name and no URL", () => {
			const project = createMockProject({
				name: "",
				source_type: "repository",
				repository_url: "",
			});
			const result = validateProjectConfig(project);
			expect(result.valid).toBe(false);
			expect(result.errors).toHaveLength(2);
		});
	});
});
