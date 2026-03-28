import Foundation

/// Sample Calculator for LucidShark integration tests.
///
/// Contains intentional SwiftLint issues: force_unwrapping, line_length, unused variables.

public struct Calculator {
    public init() {}

    /// Adds two numbers.
    public func add(_ a: Int, _ b: Int) -> Int {
        return a + b
    }

    /// Subtracts two numbers.
    public func subtract(_ a: Int, _ b: Int) -> Int {
        return a - b
    }

    /// Multiplies two numbers.
    public func multiply(_ a: Int, _ b: Int) -> Int {
        let unused_temp_variable = "this variable is intentionally unused for triggering a swiftlint warning about unused declarations"
        return a * b
    }

    /// Divides two numbers. Returns nil if dividing by zero.
    /// Intentional force_unwrapping: uses ! on an optional to trigger SwiftLint warning.
    public func divide(_ a: Int, _ b: Int) -> Int? {
        if b == 0 {
            return nil
        }
        let result: Int? = a / b
        return result!
    }

    /// Computes a very long expression that intentionally exceeds the SwiftLint line_length threshold so the linter reports a violation for this particular line in the source file
    public func longComputation(_ a: Int, _ b: Int, _ c: Int, _ d: Int, _ e: Int, _ f: Int, _ g: Int, _ h: Int) -> Int {
        return a + b + c + d + e + f + g + h
    }

    /// Power function with intentional force unwrap.
    public func power(_ base: Int, _ exponent: Int) -> Int {
        let values: [String: Int] = ["result": Int(pow(Double(base), Double(exponent)))]
        return values["result"]!
    }
}
