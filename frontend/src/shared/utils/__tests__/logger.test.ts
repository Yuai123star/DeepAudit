import { describe, beforeEach, it, expect, vi } from "vitest";

// Provide a localStorage mock BEFORE imports are processed (vi.hoisted runs first)
vi.hoisted(() => {
	const store: Record<string, string> = {};
	const mockStorage = {
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
	vi.stubGlobal("localStorage", mockStorage);
});

// Suppress console.error from Logger constructor
const origConsoleError = console.error;
console.error = vi.fn();

import { logger, LogLevel, LogCategory } from "../logger";

// Restore console.error
console.error = origConsoleError;

describe("Logger", () => {
	beforeEach(() => {
		logger.clearLogs();
		logger.setEnabled(true);
	});

	it("log() should create an entry and add it to logs", () => {
		logger.log(LogLevel.INFO, LogCategory.SYSTEM, "test message");
		const logs = logger.getLogs();
		expect(logs.length).toBe(1);
		expect(logs[0].message).toBe("test message");
		expect(logs[0].level).toBe(LogLevel.INFO);
		expect(logs[0].category).toBe(LogCategory.SYSTEM);
	});

	it("log() should populate timestamp", () => {
		logger.log(LogLevel.INFO, LogCategory.SYSTEM, "msg");
		const entry = logger.getLogs()[0];
		expect(entry.timestamp).toBeTypeOf("number");
	});

	it("debug() should log with DEBUG level", () => {
		logger.debug(LogCategory.USER_ACTION, "debug msg");
		expect(logger.getLogs()[0].level).toBe(LogLevel.DEBUG);
	});

	it("info() should log with INFO level", () => {
		logger.info(LogCategory.API_CALL, "info msg");
		expect(logger.getLogs()[0].level).toBe(LogLevel.INFO);
	});

	it("warn() should log with WARN level", () => {
		logger.warn(LogCategory.SYSTEM, "warn msg");
		expect(logger.getLogs()[0].level).toBe(LogLevel.WARN);
	});

	it("error() should log with ERROR level", () => {
		logger.error(LogCategory.SYSTEM, "error msg");
		expect(logger.getLogs()[0].level).toBe(LogLevel.ERROR);
	});

	it("getLogs() with level filter should return only matching entries", () => {
		logger.info(LogCategory.SYSTEM, "info msg");
		logger.error(LogCategory.SYSTEM, "error msg");

		const errorLogs = logger.getLogs({ level: LogLevel.ERROR });
		expect(errorLogs.length).toBe(1);
		expect(errorLogs[0].level).toBe(LogLevel.ERROR);
	});

	it("getLogs() with category filter should return only matching entries", () => {
		logger.info(LogCategory.USER_ACTION, "user action");
		logger.info(LogCategory.API_CALL, "api call");

		const apiLogs = logger.getLogs({ category: LogCategory.API_CALL });
		expect(apiLogs.length).toBe(1);
		expect(apiLogs[0].category).toBe(LogCategory.API_CALL);
	});

	it("clearLogs() should remove all entries", () => {
		logger.info(LogCategory.SYSTEM, "msg1");
		logger.info(LogCategory.SYSTEM, "msg2");
		expect(logger.getLogs().length).toBe(2);

		logger.clearLogs();
		expect(logger.getLogs().length).toBe(0);
	});

	it("exportLogsAsJson() should return valid JSON", () => {
		logger.info(LogCategory.SYSTEM, "json-test");

		const json = logger.exportLogsAsJson();
		expect(() => JSON.parse(json)).not.toThrow();

		const parsed = JSON.parse(json);
		expect(parsed.length).toBe(1);
		expect(parsed[0].message).toBe("json-test");
	});

	it("exportLogsAsCsv() should return CSV format with headers and rows", () => {
		logger.info(LogCategory.SYSTEM, "csv-msg");

		const csv = logger.exportLogsAsCsv();
		const lines = csv.split("\n");
		expect(lines.length).toBe(2);
		expect(lines[0]).toContain("Timestamp");
		expect(lines[1]).toContain("csv-msg");
	});

	it("addListener() should be notified on log()", () => {
		const listener = vi.fn();
		logger.addListener(listener);

		logger.info(LogCategory.SYSTEM, "notify me");

		expect(listener).toHaveBeenCalledTimes(1);
		expect(listener).toHaveBeenCalledWith(
			expect.objectContaining({ message: "notify me" }),
		);
	});

	it("addListener() unsubscribe should stop notifications", () => {
		const listener = vi.fn();
		const unsubscribe = logger.addListener(listener);

		unsubscribe();
		logger.info(LogCategory.SYSTEM, "after unsubscribe");

		expect(listener).not.toHaveBeenCalled();
	});

	it("setEnabled(false) should make log() a no-op", () => {
		logger.setEnabled(false);
		logger.info(LogCategory.SYSTEM, "should not appear");

		expect(logger.getLogs().length).toBe(0);
	});

	it("setEnabled(true) should resume logging", () => {
		logger.setEnabled(false);
		logger.info(LogCategory.SYSTEM, "invisible");
		logger.setEnabled(true);
		logger.info(LogCategory.SYSTEM, "visible");

		expect(logger.getLogs().length).toBe(1);
		expect(logger.getLogs()[0].message).toBe("visible");
	});

	it("getStats() should return correct counts", () => {
		logger.info(LogCategory.SYSTEM, "a");
		logger.info(LogCategory.API_CALL, "b");
		logger.error(LogCategory.SYSTEM, "c");

		const stats = logger.getStats();
		expect(stats.total).toBe(3);
		expect(stats.byLevel[LogLevel.INFO]).toBe(2);
		expect(stats.byLevel[LogLevel.ERROR]).toBe(1);
		expect(stats.byCategory[LogCategory.SYSTEM]).toBe(2);
		expect(stats.errors).toBe(1);
	});

	it("log() with data should include data in the entry", () => {
		logger.info(LogCategory.SYSTEM, "with-data", { foo: "bar" });
		const entry = logger.getLogs()[0];
		expect(entry.data).toEqual({ foo: "bar" });
	});
});
