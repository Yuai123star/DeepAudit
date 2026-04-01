import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useDebounce } from "../useDebounce";

describe("useDebounce", () => {
	it("returns initial value immediately", () => {
		const { result } = renderHook(() => useDebounce("hello", 500));
		expect(result.current).toBe("hello");
	});

	it("updates value after delay", () => {
		vi.useFakeTimers();
		const { result, rerender } = renderHook(
			({ value, delay }) => useDebounce(value, delay),
			{ initialProps: { value: "hello", delay: 500 } },
		);

		rerender({ value: "world", delay: 500 });
		expect(result.current).toBe("hello");

		act(() => {
			vi.advanceTimersByTime(500);
		});
		expect(result.current).toBe("world");

		vi.useRealTimers();
	});

	it("resets timer on rapid changes", () => {
		vi.useFakeTimers();
		const { result, rerender } = renderHook(
			({ value, delay }) => useDebounce(value, delay),
			{ initialProps: { value: "a", delay: 500 } },
		);

		rerender({ value: "b", delay: 500 });
		act(() => {
			vi.advanceTimersByTime(300);
		});

		rerender({ value: "c", delay: 500 });
		act(() => {
			vi.advanceTimersByTime(300);
		});
		expect(result.current).toBe("a");

		act(() => {
			vi.advanceTimersByTime(200);
		});
		expect(result.current).toBe("c");

		vi.useRealTimers();
	});

	it("works with numeric values", () => {
		vi.useFakeTimers();
		const { result, rerender } = renderHook(
			({ value }) => useDebounce(value, 100),
			{ initialProps: { value: 0 } },
		);

		rerender({ value: 42 });
		act(() => {
			vi.advanceTimersByTime(100);
		});
		expect(result.current).toBe(42);

		vi.useRealTimers();
	});

	it("handles delay change", () => {
		vi.useFakeTimers();
		const { result, rerender } = renderHook(
			({ value, delay }) => useDebounce(value, delay),
			{ initialProps: { value: "a", delay: 500 } },
		);

		rerender({ value: "b", delay: 200 });
		act(() => {
			vi.advanceTimersByTime(200);
		});
		expect(result.current).toBe("b");

		vi.useRealTimers();
	});
});
