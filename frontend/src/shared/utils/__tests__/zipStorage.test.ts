import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the apiClient module before importing zipStorage
vi.mock("@/shared/api/serverClient", () => ({
	apiClient: {
		get: vi.fn(),
		post: vi.fn(),
		delete: vi.fn(),
	},
}));

import { apiClient } from "@/shared/api/serverClient";
import {
	getZipFileInfo,
	uploadZipFile,
	deleteZipFile,
	hasZipFile,
	formatFileSize,
} from "@/shared/utils/zipStorage";

describe("zipStorage", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	describe("getZipFileInfo", () => {
		it("should return zip file info on successful response", async () => {
			const mockData = {
				has_file: true,
				original_filename: "project.zip",
				file_size: 1024,
				uploaded_at: "2025-01-01T00:00:00Z",
			};
			(apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
				data: mockData,
			});

			const result = await getZipFileInfo("project-1");
			expect(result).toEqual(mockData);
			expect(apiClient.get).toHaveBeenCalledWith("/projects/project-1/zip");
		});

		it("should return has_file: false when the API call fails", async () => {
			(apiClient.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
				new Error("Network error"),
			);

			const result = await getZipFileInfo("project-1");
			expect(result).toEqual({ has_file: false });
		});
	});

	describe("uploadZipFile", () => {
		it("should upload a file and return success response", async () => {
			const mockResponse = {
				message: "Uploaded",
				original_filename: "project.zip",
				file_size: 2048,
			};
			(apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
				data: mockResponse,
			});

			const file = new File(["content"], "project.zip", {
				type: "application/zip",
			});
			const result = await uploadZipFile("project-1", file);

			expect(result.success).toBe(true);
			expect(result.original_filename).toBe("project.zip");
			expect(result.file_size).toBe(2048);
			expect(apiClient.post).toHaveBeenCalledWith(
				"/projects/project-1/zip",
				expect.any(FormData),
				{
					headers: { "Content-Type": "multipart/form-data" },
				},
			);
		});

		it("should return failure when the upload fails", async () => {
			const error = {
				response: { data: { detail: "File too large" } },
			};
			(apiClient.post as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
				error,
			);

			const file = new File(["content"], "big.zip", {
				type: "application/zip",
			});
			const result = await uploadZipFile("project-1", file);

			expect(result.success).toBe(false);
			expect(result.message).toBe("File too large");
		});

		it("should return default error message when error has no detail", async () => {
			(apiClient.post as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
				new Error("Unknown error"),
			);

			const file = new File(["content"], "test.zip", {
				type: "application/zip",
			});
			const result = await uploadZipFile("project-1", file);

			expect(result.success).toBe(false);
			expect(result.message).toBe("\u4E0A\u4F20\u5931\u8D25");
		});
	});

	describe("deleteZipFile", () => {
		it("should return true on successful deletion", async () => {
			(apiClient.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
				undefined,
			);

			const result = await deleteZipFile("project-1");
			expect(result).toBe(true);
			expect(apiClient.delete).toHaveBeenCalledWith("/projects/project-1/zip");
		});

		it("should return false when deletion fails", async () => {
			(apiClient.delete as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
				new Error("Network error"),
			);

			const result = await deleteZipFile("project-1");
			expect(result).toBe(false);
		});
	});

	describe("hasZipFile", () => {
		it("should return true when zip file exists", async () => {
			(apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
				data: { has_file: true },
			});

			const result = await hasZipFile("project-1");
			expect(result).toBe(true);
		});

		it("should return false when zip file does not exist", async () => {
			(apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
				data: { has_file: false },
			});

			const result = await hasZipFile("project-1");
			expect(result).toBe(false);
		});

		it("should return false when API call fails", async () => {
			(apiClient.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
				new Error("Network error"),
			);

			const result = await hasZipFile("project-1");
			expect(result).toBe(false);
		});
	});

	describe("formatFileSize", () => {
		it("should format bytes correctly (less than 1 KB)", () => {
			expect(formatFileSize(512)).toBe("512 B");
		});

		it("should format bytes correctly (0 bytes)", () => {
			expect(formatFileSize(0)).toBe("0 B");
		});

		it("should format kilobytes correctly", () => {
			expect(formatFileSize(1536)).toBe("1.50 KB");
		});

		it("should format megabytes correctly", () => {
			expect(formatFileSize(2 * 1024 * 1024)).toBe("2.00 MB");
		});

		it("should format exactly 1 KB boundary", () => {
			expect(formatFileSize(1024)).toBe("1.00 KB");
		});

		it("should format exactly 1 MB boundary", () => {
			expect(formatFileSize(1024 * 1024)).toBe("1.00 MB");
		});
	});
});
