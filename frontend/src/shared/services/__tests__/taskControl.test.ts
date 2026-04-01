import { describe, beforeEach, afterEach, it, expect, vi } from "vitest";

// Mock the database module so cancelAuditTask does not hit the real API
vi.mock("@/shared/api/database", () => ({
	api: {
		cancelAuditTask: vi.fn().mockResolvedValue(undefined),
	},
}));

import { taskControl } from "../taskControl";
import { api } from "@/shared/api/database";

describe("TaskControl", () => {
	beforeEach(() => {
		taskControl.clearAll();
		vi.clearAllMocks();
	});

	afterEach(() => {
		taskControl.clearAll();
	});

	it("cancelTask() should add task to cancelled set", () => {
		taskControl.cancelTask("task-1");

		expect(taskControl.isCancelled("task-1")).toBe(true);
	});

	it("cancelTask() should call api.cancelAuditTask with the taskId", () => {
		taskControl.cancelTask("task-abc");

		expect(api.cancelAuditTask).toHaveBeenCalledWith("task-abc");
	});

	it("isCancelled() should return false for unknown tasks", () => {
		expect(taskControl.isCancelled("nonexistent")).toBe(false);
	});

	it("isCancelled() should return true for cancelled tasks", () => {
		taskControl.cancelTask("task-x");
		expect(taskControl.isCancelled("task-x")).toBe(true);
	});

	it("clearCancelled() should remove a specific task from the cancelled set", () => {
		taskControl.cancelTask("task-a");
		taskControl.cancelTask("task-b");

		taskControl.clearCancelled("task-a");

		expect(taskControl.isCancelled("task-a")).toBe(false);
		expect(taskControl.isCancelled("task-b")).toBe(true);
	});

	it("clearAll() should remove all cancelled tasks", () => {
		taskControl.cancelTask("task-1");
		taskControl.cancelTask("task-2");
		taskControl.cancelTask("task-3");

		taskControl.clearAll();

		expect(taskControl.isCancelled("task-1")).toBe(false);
		expect(taskControl.isCancelled("task-2")).toBe(false);
		expect(taskControl.isCancelled("task-3")).toBe(false);
	});

	it("cancelTask() should handle API call failure gracefully", () => {
		const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
		vi.mocked(api.cancelAuditTask).mockRejectedValueOnce(new Error("network error"));

		taskControl.cancelTask("task-fail");

		// Task should still be marked as cancelled even if API fails
		expect(taskControl.isCancelled("task-fail")).toBe(true);

		// Wait for the async catch to fire
		return vi.waitFor(() => {
			expect(consoleErrorSpy).toHaveBeenCalled();
		}).finally(() => {
			consoleErrorSpy.mockRestore();
		});
	});
});
