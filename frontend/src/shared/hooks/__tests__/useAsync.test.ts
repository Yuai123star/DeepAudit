import { renderHook, act, waitFor } from "@testing-library/react";
import { useAsync, useAsyncCallback } from "../useAsync";

describe("useAsync", () => {
	it("should start with loading=true and null data", () => {
		const asyncFn = vi.fn().mockImplementation(() => new Promise(() => {}));
		const { result } = renderHook(() => useAsync(asyncFn));

		expect(result.current.loading).toBe(true);
		expect(result.current.data).toBeNull();
		expect(result.current.error).toBeNull();
	});

	it("should set data on successful resolution", async () => {
		const asyncFn = vi.fn().mockResolvedValue("test-data");
		const { result } = renderHook(() => useAsync(asyncFn));

		await waitFor(() => {
			expect(result.current.loading).toBe(false);
		});

		expect(result.current.data).toBe("test-data");
		expect(result.current.error).toBeNull();
	});

	it("should set error on rejection", async () => {
		const error = new Error("test error");
		const asyncFn = vi.fn().mockRejectedValue(error);
		const { result } = renderHook(() => useAsync(asyncFn));

		await waitFor(() => {
			expect(result.current.loading).toBe(false);
		});

		expect(result.current.data).toBeNull();
		expect(result.current.error).toBe(error);
	});

	it("should auto-execute on mount", () => {
		const asyncFn = vi.fn().mockResolvedValue("data");
		renderHook(() => useAsync(asyncFn));

		expect(asyncFn).toHaveBeenCalledTimes(1);
	});

	it("should provide a refetch function", async () => {
		const asyncFn = vi.fn().mockResolvedValue("data");
		const { result } = renderHook(() => useAsync(asyncFn));

		await waitFor(() => {
			expect(result.current.loading).toBe(false);
		});

		expect(typeof result.current.refetch).toBe("function");
	});

	it("should re-execute when refetch is called", async () => {
		const asyncFn = vi.fn().mockResolvedValue("data");
		const { result } = renderHook(() => useAsync(asyncFn));

		await waitFor(() => {
			expect(result.current.loading).toBe(false);
		});

		expect(asyncFn).toHaveBeenCalledTimes(1);

		await act(async () => {
			await result.current.refetch();
		});

		expect(asyncFn).toHaveBeenCalledTimes(2);
	});

	it("should re-execute when dependencies change", async () => {
		const asyncFn = vi.fn().mockResolvedValue("data");
		const { result, rerender } = renderHook(
			({ dep }: { dep: number }) => useAsync(asyncFn, [dep]),
			{ initialProps: { dep: 1 } },
		);

		await waitFor(() => {
			expect(result.current.loading).toBe(false);
		});

		expect(asyncFn).toHaveBeenCalledTimes(1);

		rerender({ dep: 2 });

		await waitFor(() => {
			expect(result.current.loading).toBe(false);
		});

		expect(asyncFn).toHaveBeenCalledTimes(2);
	});

	it("should not re-execute when dependencies are the same", async () => {
		const asyncFn = vi.fn().mockResolvedValue("data");
		const { result, rerender } = renderHook(
			({ dep }: { dep: number }) => useAsync(asyncFn, [dep]),
			{ initialProps: { dep: 1 } },
		);

		await waitFor(() => {
			expect(result.current.loading).toBe(false);
		});

		expect(asyncFn).toHaveBeenCalledTimes(1);

		rerender({ dep: 1 });

		expect(asyncFn).toHaveBeenCalledTimes(1);
	});

	it("should handle objects as resolved data", async () => {
		const obj = { name: "test", value: 42 };
		const asyncFn = vi.fn().mockResolvedValue(obj);
		const { result } = renderHook(() => useAsync(asyncFn));

		await waitFor(() => {
			expect(result.current.loading).toBe(false);
		});

		expect(result.current.data).toEqual(obj);
	});

	it("should reset error on refetch after a previous error", async () => {
		let callCount = 0;
		const asyncFn = vi.fn().mockImplementation(() => {
			callCount++;
			if (callCount === 1) {
				return Promise.reject(new Error("first fail"));
			}
			return Promise.resolve("success");
		});

		const { result } = renderHook(() => useAsync(asyncFn));

		await waitFor(() => {
			expect(result.current.loading).toBe(false);
		});

		expect(result.current.error).not.toBeNull();

		await act(async () => {
			await result.current.refetch();
		});

		expect(result.current.error).toBeNull();
		expect(result.current.data).toBe("success");
	});
});

describe("useAsyncCallback", () => {
	it("should start with loading=false and null data", () => {
		const asyncFn = vi.fn().mockResolvedValue("data");
		const { result } = renderHook(() => useAsyncCallback(asyncFn));

		const [, state] = result.current;
		expect(state.loading).toBe(false);
		expect(state.data).toBeNull();
		expect(state.error).toBeNull();
	});

	it("should NOT auto-execute on mount", () => {
		const asyncFn = vi.fn().mockResolvedValue("data");
		renderHook(() => useAsyncCallback(asyncFn));

		expect(asyncFn).not.toHaveBeenCalled();
	});

	it("should execute when called with arguments", async () => {
		const asyncFn = vi.fn().mockResolvedValue("result");
		const { result } = renderHook(() => useAsyncCallback(asyncFn));

		const [execute] = result.current;

		await act(async () => {
			await execute("arg1", "arg2");
		});

		expect(asyncFn).toHaveBeenCalledWith("arg1", "arg2");
	});

	it("should set data on successful execution", async () => {
		const asyncFn = vi.fn().mockResolvedValue("result-data");
		const { result } = renderHook(() => useAsyncCallback(asyncFn));

		const [execute] = result.current;

		await act(async () => {
			await execute();
		});

		const [, state] = result.current;
		expect(state.data).toBe("result-data");
		expect(state.loading).toBe(false);
		expect(state.error).toBeNull();
	});

	it("should set error on failed execution", async () => {
		const asyncFn = vi.fn().mockRejectedValue(new Error("callback error"));
		const { result } = renderHook(() => useAsyncCallback(asyncFn));

		const [execute] = result.current;

		await act(async () => {
			await execute();
		});

		const [, state] = result.current;
		expect(state.error).toEqual(new Error("callback error"));
		expect(state.loading).toBe(false);
	});
});
