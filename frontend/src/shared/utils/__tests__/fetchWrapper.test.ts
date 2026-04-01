import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Use vi.hoisted to create the mock function before any module evaluation
const mockFetch = vi.hoisted(() => vi.fn());

// Replace window.fetch BEFORE fetchWrapper module loads, so originalFetch captures our mock
vi.hoisted(() => {
	window.fetch = mockFetch;
});

// Mock logger before fetchWrapper imports it
vi.mock("@/shared/utils/logger", () => ({
	logger: {
		error: vi.fn(),
		info: vi.fn(),
		warn: vi.fn(),
		logPerformance: vi.fn(),
	},
	LogCategory: {
		USER_ACTION: "USER_ACTION",
		API_CALL: "API_CALL",
		SYSTEM: "SYSTEM",
		CONSOLE_ERROR: "CONSOLE_ERROR",
	},
}));

import { logger, LogCategory } from "@/shared/utils/logger";
import { originalFetch } from "@/shared/utils/fetchWrapper";

describe("fetchWrapper", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	it("should capture the pre-existing fetch as originalFetch", () => {
		// originalFetch should be our mockFetch since we set it before module load
		expect(originalFetch).toBe(mockFetch);
	});

	it("should replace window.fetch with a wrapper function", () => {
		expect(window.fetch).not.toBe(mockFetch);
		expect(typeof window.fetch).toBe("function");
	});

	it("should pass through successful responses without logging errors", async () => {
		const mockResponse = new Response(JSON.stringify({ ok: true }), {
			status: 200,
			statusText: "OK",
		});
		mockFetch.mockResolvedValueOnce(mockResponse);

		const response = await window.fetch("/api/v1/test");

		expect(mockFetch).toHaveBeenCalledTimes(1);
		expect(response.status).toBe(200);
		expect(response.ok).toBe(true);
		expect(logger.error).not.toHaveBeenCalled();
	});

	it("should use GET as default method when no options provided", async () => {
		mockFetch.mockResolvedValueOnce(
			new Response(null, { status: 500, statusText: "Error" }),
		);

		await window.fetch("/api/v1/test");

		expect(logger.error).toHaveBeenCalledWith(
			LogCategory.API_CALL,
			expect.any(String),
			expect.objectContaining({ method: "GET" }),
		);
	});

	it("should pass through POST, PUT, DELETE methods", async () => {
		mockFetch.mockResolvedValue(
			new Response(null, { status: 500, statusText: "Error" }),
		);

		await window.fetch("/api/v1/test", { method: "POST", body: "data" });
		await window.fetch("/api/v1/test", { method: "PUT", body: "data" });
		await window.fetch("/api/v1/test", { method: "DELETE" });

		expect(mockFetch).toHaveBeenCalledTimes(3);
		expect(mockFetch).toHaveBeenNthCalledWith(1, "/api/v1/test", {
			method: "POST",
			body: "data",
		});
		expect(mockFetch).toHaveBeenNthCalledWith(2, "/api/v1/test", {
			method: "PUT",
			body: "data",
		});
		expect(mockFetch).toHaveBeenNthCalledWith(3, "/api/v1/test", {
			method: "DELETE",
		});

		// Verify method in error logs
		const calls = (logger.error as ReturnType<typeof vi.fn>).mock.calls;
		expect(calls[0][2].method).toBe("POST");
		expect(calls[1][2].method).toBe("PUT");
		expect(calls[2][2].method).toBe("DELETE");
	});

	it("should log error for failed HTTP responses (non-ok)", async () => {
		const errorResponse = new Response(JSON.stringify({ error: "fail" }), {
			status: 500,
			statusText: "Internal Server Error",
		});
		mockFetch.mockResolvedValueOnce(errorResponse);

		const response = await window.fetch("/api/v1/fail");

		expect(response.status).toBe(500);
		expect(logger.error).toHaveBeenCalledTimes(1);
		expect(logger.error).toHaveBeenCalledWith(
			LogCategory.API_CALL,
			expect.stringContaining("500"),
			expect.objectContaining({
				status: 500,
				method: "GET",
			}),
		);
	});

	it("should log error and rethrow when fetch throws a network error", async () => {
		const networkError = new TypeError("Failed to fetch");
		mockFetch.mockRejectedValueOnce(networkError);

		await expect(window.fetch("/api/v1/network-fail")).rejects.toThrow(
			"Failed to fetch",
		);

		expect(logger.error).toHaveBeenCalledTimes(1);
		expect(logger.error).toHaveBeenCalledWith(
			LogCategory.API_CALL,
			expect.stringContaining("API\u8BF7\u6C42\u5F02\u5E38"),
			expect.objectContaining({
				method: "GET",
				error: "Failed to fetch",
			}),
			expect.any(String),
		);
	});

	it("should skip logging for static resource URLs (images, fonts)", async () => {
		mockFetch.mockResolvedValue(
			new Response(null, { status: 500, statusText: "Error" }),
		);

		await window.fetch("/assets/logo.png");
		await window.fetch("/assets/icon.svg");
		await window.fetch("/fonts/roboto.woff2");

		// Static resources should bypass logging entirely
		expect(logger.error).not.toHaveBeenCalled();
		expect(mockFetch).toHaveBeenCalledTimes(3);
	});

	it("should handle non-string URL inputs (Request objects)", async () => {
		mockFetch.mockResolvedValueOnce(
			new Response(null, { status: 200, statusText: "OK" }),
		);

		const request = new Request("http://localhost/api/v1/test");
		const response = await window.fetch(request);

		expect(response.status).toBe(200);
		expect(mockFetch).toHaveBeenCalledTimes(1);
	});

	it("should include duration in error logs for both HTTP and network errors", async () => {
		// HTTP error
		mockFetch.mockResolvedValueOnce(
			new Response(null, { status: 404, statusText: "Not Found" }),
		);
		await window.fetch("/api/v1/missing");

		expect(logger.error).toHaveBeenCalledWith(
			LogCategory.API_CALL,
			expect.any(String),
			expect.objectContaining({
				status: 404,
				duration: expect.any(Number),
			}),
		);

		vi.clearAllMocks();

		// Network error
		mockFetch.mockRejectedValueOnce(new Error("Network error"));
		try {
			await window.fetch("/api/v1/test");
		} catch {
			// expected
		}

		expect(logger.error).toHaveBeenCalledWith(
			LogCategory.API_CALL,
			expect.any(String),
			expect.objectContaining({
				duration: expect.any(Number),
			}),
			expect.any(String),
		);
	});
});
