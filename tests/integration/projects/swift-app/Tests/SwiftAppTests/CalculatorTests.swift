import XCTest
@testable import SwiftApp

final class CalculatorTests: XCTestCase {
    var calculator: Calculator!

    override func setUp() {
        super.setUp()
        calculator = Calculator()
    }

    func testAdd() {
        XCTAssertEqual(calculator.add(2, 3), 5)
        XCTAssertEqual(calculator.add(-1, 1), 0)
        XCTAssertEqual(calculator.add(0, 0), 0)
    }

    func testSubtract() {
        XCTAssertEqual(calculator.subtract(5, 3), 2)
        XCTAssertEqual(calculator.subtract(3, 5), -2)
        XCTAssertEqual(calculator.subtract(0, 0), 0)
    }

    func testMultiply() {
        XCTAssertEqual(calculator.multiply(2, 3), 6)
        XCTAssertEqual(calculator.multiply(-2, 3), -6)
        XCTAssertEqual(calculator.multiply(0, 100), 0)
    }

    func testDivide() {
        XCTAssertEqual(calculator.divide(6, 3), 2)
        XCTAssertEqual(calculator.divide(10, 2), 5)
        XCTAssertEqual(calculator.divide(7, 2), 3)
    }

    func testDivideByZero() {
        XCTAssertNil(calculator.divide(1, 0))
        XCTAssertNil(calculator.divide(0, 0))
    }
}
