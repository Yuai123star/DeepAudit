import { renderHook, act } from "@testing-library/react";
import { useLocalStorage, useSessionStorage } from "../useLocalStorage";

describe("useLocalStorage", () => {
	it("should return initial value when storage is empty", () => {
		const { result } = renderHook(() => useLocalStorage("test-key-1", "default"));
		expect(result.current[0]).toBe("default");
	});

	it("should set a new value and update state", () => {
		const { result } = renderHook(() =>
			useLocalStorage("set-test-key-1", "initial"),
		);

		act(() => {
			result.current[1]("new-value");
		});

		expect(result.current[0]).toBe("new-value");
	});

	it("should support functional updater", () => {
		const { result } = renderHook(() => useLocalStorage("counter-1", 10));

		act(() => {
			result.current[1]((prev: number) => prev + 5);
		});

		expect(result.current[0]).toBe(15);
	});
});

describe("useSessionStorage", () => {
	it("should return initial value when storage is empty", () => {
		const { result } = renderHook(() =>
			useSessionStorage("sess-key-1", "default"),
		);
		expect(result.current[0]).toBe("default");
	});

	it("should set a new value and update state", () => {
		const { result } = renderHook(() =>
			useSessionStorage("sess-write-1", 0),
		);

		act(() => {
			result.current[1](42);
		});

		expect(result.current[0]).toBe(42);
	});
});
