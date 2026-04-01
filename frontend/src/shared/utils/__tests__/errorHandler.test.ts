import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock sonner toast
vi.mock("sonner", () => ({
	toast: {
		error: vi.fn(),
	},
}));

// Mock logger module
vi.mock("../logger", () => ({
	logger: {
		error: vi.fn(),
		info: vi.fn(),
		warn: vi.fn(),
		debug: vi.fn(),
		log: vi.fn(),
	},
	LogCategory: {
		USER_ACTION: "USER_ACTION",
		API_CALL: "API_CALL",
		SYSTEM: "SYSTEM",
		CONSOLE_ERROR: "CONSOLE_ERROR",
	},
}));

import { ErrorType, errorHandler, handleError, wrapAsync, wrapSync } from "../errorHandler";
import { toast } from "sonner";
import { logger, LogCategory } from "../logger";

beforeEach(() => {
	vi.clearAllMocks();
});

// ============ ErrorType enum ============

describe("ErrorType", () => {
	it("has all expected error types", () => {
		expect(ErrorType.NETWORK).toBe("NETWORK");
		expect(ErrorType.API).toBe("API");
		expect(ErrorType.VALIDATION).toBe("VALIDATION");
		expect(ErrorType.AUTHENTICATION).toBe("AUTHENTICATION");
		expect(ErrorType.AUTHORIZATION).toBe("AUTHORIZATION");
		expect(ErrorType.NOT_FOUND).toBe("NOT_FOUND");
		expect(ErrorType.TIMEOUT).toBe("TIMEOUT");
		expect(ErrorType.UNKNOWN).toBe("UNKNOWN");
	});
});

// ============ createError ============

describe("createError", () => {
	it("creates an AppError with correct type and message", () => {
		const err = errorHandler.createError(ErrorType.NETWORK, "connection lost");
		expect(err.type).toBe(ErrorType.NETWORK);
		expect(err.message).toBe("connection lost");
		expect(err.timestamp).toBeGreaterThan(0);
	});

	it("includes details when provided", () => {
		const details = { url: "/api/test" };
		const err = errorHandler.createError(ErrorType.API, "api failed", details);
		expect(err.details).toEqual(details);
	});

	it("does not include details when omitted", () => {
		const err = errorHandler.createError(ErrorType.VALIDATION, "bad input");
		expect(err.details).toBeUndefined();
	});
});

// ============ handle - parsing standard errors ============

describe("handle", () => {
	it("parses standard Error objects", () => {
		const error = new Error("something went wrong");
		const result = errorHandler.handle(error);

		expect(result.type).toBe(ErrorType.UNKNOWN);
		expect(result.message).toBe("something went wrong");
		expect(result.originalError).toBe(error);
		expect(result.timestamp).toBeGreaterThan(0);
	});

	it("parses string errors", () => {
		const result = errorHandler.handle("plain string error");
		expect(result.type).toBe(ErrorType.UNKNOWN);
		expect(result.message).toBe("plain string error");
	});

	it("parses non-Error, non-string objects", () => {
		const result = errorHandler.handle({ custom: "object" });
		expect(result.type).toBe(ErrorType.UNKNOWN);
		expect(result.message).toBe("发生未知错误");
	});

	it("parses custom AppError objects", () => {
		const appError = {
			type: ErrorType.VALIDATION,
			message: "field required",
		};
		const result = errorHandler.handle(appError);
		expect(result.type).toBe(ErrorType.VALIDATION);
		expect(result.message).toBe("field required");
	});

	it("logs error via logger", () => {
		errorHandler.handle(new Error("test"));
		expect(logger.error).toHaveBeenCalled();
	});

	it("shows toast via sonner", () => {
		errorHandler.handle(new Error("test"));
		expect(toast.error).toHaveBeenCalled();
	});

	it("prepends context to log message", () => {
		errorHandler.handle(new Error("test"), "MyContext");
		expect(logger.error).toHaveBeenCalledWith(
			LogCategory.SYSTEM,
			expect.stringContaining("[MyContext]"),
			expect.any(Object),
			expect.any(String),
		);
	});
});

// ============ handle - parsing Axios errors ============

describe("handle - Axios errors", () => {
	it("parses Axios error without response as NETWORK error", () => {
		const axiosError = { isAxiosError: true };
		const result = errorHandler.handle(axiosError);
		expect(result.type).toBe(ErrorType.NETWORK);
		expect(result.message).toContain("网络请求失败");
	});

	it("parses 400 status as VALIDATION error", () => {
		const error = {
			isAxiosError: true,
			response: { status: 400, data: { message: "invalid field" } },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.VALIDATION);
		expect(result.message).toBe("invalid field");
		expect(result.code).toBe(400);
	});

	it("parses 400 with no data message using default", () => {
		const error = {
			response: { status: 400, data: {} },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.VALIDATION);
		expect(result.message).toBe("请求参数错误");
	});

	it("parses 401 status as AUTHENTICATION error", () => {
		const error = {
			response: { status: 401, data: {} },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.AUTHENTICATION);
		expect(result.message).toContain("登录");
		expect(result.code).toBe(401);
	});

	it("parses 403 status as AUTHORIZATION error", () => {
		const error = {
			response: { status: 403, data: {} },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.AUTHORIZATION);
		expect(result.message).toContain("权限");
	});

	it("parses 404 status as NOT_FOUND error", () => {
		const error = {
			response: { status: 404, data: {} },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.NOT_FOUND);
		expect(result.message).toContain("不存在");
	});

	it("parses 408 status as TIMEOUT error", () => {
		const error = {
			response: { status: 408, data: {} },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.TIMEOUT);
		expect(result.code).toBe(408);
	});

	it("parses 504 status as TIMEOUT error", () => {
		const error = {
			response: { status: 504, data: {} },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.TIMEOUT);
		expect(result.code).toBe(504);
	});

	it("parses 500 status as API error", () => {
		const error = {
			response: { status: 500, data: { detail: "internal" } },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.API);
		expect(result.message).toContain("服务器错误");
		expect(result.code).toBe(500);
	});

	it("parses 502 status as API error", () => {
		const error = {
			response: { status: 502, data: {} },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.API);
		expect(result.code).toBe(502);
	});

	it("parses 503 status as API error", () => {
		const error = {
			response: { status: 503, data: {} },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.API);
		expect(result.code).toBe(503);
	});

	it("parses unknown status codes as API error with status code in message", () => {
		const error = {
			response: { status: 418, data: { message: "I'm a teapot" } },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.API);
		expect(result.code).toBe(418);
		expect(result.message).toBe("I'm a teapot");
	});

	it("parses unknown status codes without message using default format", () => {
		const error = {
			response: { status: 429, data: {} },
		};
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.API);
		expect(result.message).toContain("429");
	});
});

// ============ handle - parsing fetch TypeError ============

describe("handle - fetch TypeError", () => {
	it("parses TypeError with 'fetch' as NETWORK error", () => {
		const error = new TypeError("Failed to fetch");
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.NETWORK);
		expect(result.message).toContain("网络连接失败");
	});

	it("does not treat other TypeErrors as NETWORK errors", () => {
		const error = new TypeError("Cannot read property of undefined");
		const result = errorHandler.handle(error);
		expect(result.type).toBe(ErrorType.UNKNOWN);
	});
});

// ============ wrap (async) ============

describe("wrap", () => {
	it("returns the result on success", async () => {
		const result = await errorHandler.wrap(() => Promise.resolve(42));
		expect(result).toBe(42);
	});

	it("catches error, calls handle, and returns undefined by default", async () => {
		const result = await errorHandler.wrap(() => Promise.reject(new Error("fail")));
		expect(result).toBeUndefined();
		expect(toast.error).toHaveBeenCalled();
	});

	it("returns fallback on failure", async () => {
		const result = await errorHandler.wrap(
			() => Promise.reject(new Error("fail")),
			"context",
			{ fallback: "default" },
		);
		expect(result).toBe("default");
	});

	it("does not show toast when silent is true", async () => {
		await errorHandler.wrap(
			() => Promise.reject(new Error("fail")),
			"context",
			{ silent: true },
		);
		expect(toast.error).not.toHaveBeenCalled();
		expect(logger.error).toHaveBeenCalled();
	});
});

// ============ wrapSync ============

describe("wrapSync", () => {
	it("returns the result on success", () => {
		const result = errorHandler.wrapSync(() => 42);
		expect(result).toBe(42);
	});

	it("catches error, calls handle, and returns undefined by default", () => {
		const result = errorHandler.wrapSync(() => {
			throw new Error("sync fail");
		});
		expect(result).toBeUndefined();
		expect(toast.error).toHaveBeenCalled();
	});

	it("returns fallback on failure", () => {
		const result = errorHandler.wrapSync(
			() => {
				throw new Error("sync fail");
			},
			"syncCtx",
			{ fallback: 0 },
		);
		expect(result).toBe(0);
	});

	it("does not show toast when silent is true", () => {
		errorHandler.wrapSync(
			() => {
				throw new Error("sync fail");
			},
			"syncCtx",
			{ silent: true },
		);
		expect(toast.error).not.toHaveBeenCalled();
		expect(logger.error).toHaveBeenCalled();
	});
});

// ============ Singleton and convenience exports ============

describe("exports", () => {
	it("handleError delegates to errorHandler.handle", () => {
		const result = handleError("test error");
		expect(result.type).toBe(ErrorType.UNKNOWN);
		expect(result.message).toBe("test error");
	});

	it("wrapAsync delegates to errorHandler.wrap", async () => {
		const result = await wrapAsync(() => Promise.resolve("ok"));
		expect(result).toBe("ok");
	});

	it("wrapSync delegates to errorHandler.wrapSync", () => {
		const result = wrapSync(() => "ok");
		expect(result).toBe("ok");
	});
});
