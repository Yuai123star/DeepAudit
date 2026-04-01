import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock logger before performanceMonitor imports it
vi.mock("@/shared/utils/logger", () => ({
	logger: {
		logPerformance: vi.fn(),
		info: vi.fn(),
		error: vi.fn(),
		warn: vi.fn(),
	},
}));

import { performanceMonitor } from "@/shared/utils/performanceMonitor";
import { logger } from "@/shared/utils/logger";

describe("PerformanceMonitor", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	it("should start and end a measurement, returning the duration", () => {
		const label = "test-operation";

		performanceMonitor.start(label);
		const duration = performanceMonitor.end(label);

		expect(duration).toBeGreaterThanOrEqual(0);
		expect(logger.logPerformance).toHaveBeenCalledWith(
			label,
			expect.any(Number),
		);
	});

	it("should return 0 when ending a measurement that was never started", () => {
		const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

		const duration = performanceMonitor.end("nonexistent-label");

		expect(duration).toBe(0);
		expect(warnSpy).toHaveBeenCalledWith(
			expect.stringContaining("nonexistent-label"),
		);
	});

	it("should log to console when logToConsole is true", () => {
		const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

		performanceMonitor.start("console-test");
		performanceMonitor.end("console-test", true);

		expect(logSpy).toHaveBeenCalledWith(
			expect.stringContaining("console-test"),
		);
	});

	it("should not log to console when logToConsole is false (default)", () => {
		const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

		performanceMonitor.start("silent-test");
		performanceMonitor.end("silent-test");

		expect(logSpy).not.toHaveBeenCalled();
	});

	it("should measure an async function and return its result", async () => {
		const result = await performanceMonitor.measure("async-op", async () => {
			return 42;
		});

		expect(result).toBe(42);
		expect(logger.logPerformance).toHaveBeenCalledWith(
			"async-op",
			expect.any(Number),
		);
	});

	it("should measure a sync function and return its result", async () => {
		const result = await performanceMonitor.measure("sync-op", () => {
			return "hello";
		});

		expect(result).toBe("hello");
	});

	it("should re-throw errors from the measured function while still recording timing", async () => {
		await expect(
			performanceMonitor.measure("failing-op", () => {
				throw new Error("boom");
			}),
		).rejects.toThrow("boom");

		// Even on failure, performance should still be logged
		expect(logger.logPerformance).toHaveBeenCalledWith(
			"failing-op",
			expect.any(Number),
		);
	});

	it("should not allow ending the same mark twice (it is deleted after first end)", () => {
		const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

		performanceMonitor.start("double-end");
		performanceMonitor.end("double-end");
		const secondEnd = performanceMonitor.end("double-end");

		expect(secondEnd).toBe(0);
		expect(warnSpy).toHaveBeenCalled();
	});

	it("initAll should not throw", () => {
		expect(() => performanceMonitor.initAll()).not.toThrow();
	});
});
