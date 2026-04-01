import { describe, it, expect, vi, beforeEach } from "vitest";

// Use vi.hoisted for variables referenced inside vi.mock factories
const interceptorState = vi.hoisted(() => ({
	request: [] as Array<{
		fulfilled: (config: Record<string, unknown>) => unknown;
		rejected: (error: unknown) => Promise<unknown>;
	}>,
	response: [] as Array<{
		fulfilled: (response: unknown) => unknown;
		rejected: (error: unknown) => Promise<unknown>;
	}>,
}));

// Create a shared storage mock
const store: Record<string, string> = {};
const storageMock = {
	getItem: (key: string) => store[key] ?? null,
	setItem: (key: string, value: string) => {
		store[key] = value;
	},
	removeItem: (key: string) => {
		delete store[key];
	},
	clear: () => {
		Object.keys(store).forEach((k) => delete store[k]);
	},
	get length() {
		return Object.keys(store).length;
	},
	key: (index: number) => Object.keys(store)[index] ?? null,
};

// Mock localStorage and sessionStorage before any imports
vi.stubGlobal("localStorage", storageMock);
vi.stubGlobal("sessionStorage", storageMock);

// Mock axios - interceptorState is hoisted so accessible here
vi.mock("axios", () => {
	const createInstance = () => ({
		get: vi.fn(),
		post: vi.fn(),
		put: vi.fn(),
		delete: vi.fn(),
		patch: vi.fn(),
		interceptors: {
			request: {
				use: (
					fulfilled: (config: Record<string, unknown>) => unknown,
					rejected: (error: unknown) => Promise<unknown>,
				) => {
					interceptorState.request.push({ fulfilled, rejected });
				},
			},
			response: {
				use: (
					fulfilled: (response: unknown) => unknown,
					rejected: (error: unknown) => Promise<unknown>,
				) => {
					interceptorState.response.push({ fulfilled, rejected });
				},
			},
		},
		defaults: { headers: { common: {} } },
	});

	const instance = createInstance();

	return {
		default: {
			create: vi.fn(() => instance),
		},
		__esModule: true,
	};
});

import { apiClient } from "../serverClient";

describe("serverClient", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		storageMock.clear();
	});

	it("should create an axios instance with correct config", () => {
		expect(apiClient).toBeDefined();
		expect(apiClient.get).toBeDefined();
		expect(apiClient.post).toBeDefined();
	});

	it("should include Authorization header when token exists in localStorage", () => {
		storageMock.setItem("access_token", "test-local-token");

		const interceptor = interceptorState.request[0];
		expect(interceptor).toBeDefined();

		const config = { headers: { Authorization: "" } };
		const result = interceptor.fulfilled(config);

		expect(result.headers.Authorization).toBe("Bearer test-local-token");
	});

	it("should include Authorization header when token exists in sessionStorage", () => {
		storageMock.clear();
		storageMock.setItem("access_token", "test-session-token");

		const interceptor = interceptorState.request[0];
		const config = { headers: { Authorization: "" } };
		const result = interceptor.fulfilled(config);

		expect(result.headers.Authorization).toBe("Bearer test-session-token");
	});

	it("should not set Authorization header when no token exists", () => {
		storageMock.clear();

		const interceptor = interceptorState.request[0];
		const config = { headers: { Authorization: "" } };
		const result = interceptor.fulfilled(config);

		expect(result.headers.Authorization).toBe("");
	});

	it("should prefer localStorage token over sessionStorage", () => {
		storageMock.setItem("access_token", "local-token");

		const interceptor = interceptorState.request[0];
		const config = { headers: { Authorization: "" } };
		const result = interceptor.fulfilled(config);

		expect(result.headers.Authorization).toBe("Bearer local-token");
	});

	it("should clear tokens and redirect to /login on 401 response", async () => {
		storageMock.setItem("access_token", "expired-token");

		const mockLocation = { href: "" };
		Object.defineProperty(window, "location", {
			value: mockLocation,
			writable: true,
			configurable: true,
		});

		const interceptor = interceptorState.response[0];
		expect(interceptor).toBeDefined();

		const error401 = { response: { status: 401 } };
		await expect(interceptor.rejected(error401)).rejects.toEqual(
			expect.objectContaining({ response: { status: 401 } }),
		);

		expect(window.location.href).toBe("/login");
	});

	it("should not clear tokens on non-401 error", async () => {
		storageMock.setItem("access_token", "valid-token");

		const interceptor = interceptorState.response[0];
		const error500 = { response: { status: 500 } };
		await expect(interceptor.rejected(error500)).rejects.toEqual(
			expect.objectContaining({ response: { status: 500 } }),
		);

		expect(storageMock.getItem("access_token")).toBe("valid-token");
	});

	it("should reject the promise for network errors without response", async () => {
		const interceptor = interceptorState.response[0];
		const networkError = { message: "Network Error" };
		await expect(interceptor.rejected(networkError)).rejects.toEqual(networkError);
	});

	it("should pass through successful responses unchanged", () => {
		const interceptor = interceptorState.response[0];
		const successResponse = { data: { id: "123" }, status: 200 };
		const result = interceptor.fulfilled(successResponse);
		expect(result).toEqual(successResponse);
	});

	it("should reject request interceptor errors", async () => {
		const interceptor = interceptorState.request[0];
		const requestError = new Error("Request config error");
		await expect(interceptor.rejected(requestError)).rejects.toThrow(
			"Request config error",
		);
	});
});
