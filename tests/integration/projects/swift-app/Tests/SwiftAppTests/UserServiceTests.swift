import XCTest
@testable import SwiftApp

final class UserServiceTests: XCTestCase {
    var service: UserService!

    override func setUp() {
        super.setUp()
        service = UserService()
    }

    func testAddUser() {
        service.addUser(id: "1", name: "Alice")
        XCTAssertTrue(service.userExists(id: "1"))
    }

    func testGetUser() {
        service.addUser(id: "1", name: "Alice")
        XCTAssertEqual(service.getUser(id: "1"), "Alice")
    }

    func testUserCount() {
        XCTAssertEqual(service.getUserCount(), 0)
        service.addUser(id: "1", name: "Alice")
        XCTAssertEqual(service.getUserCount(), 1)
        service.addUser(id: "2", name: "Bob")
        XCTAssertEqual(service.getUserCount(), 2)
    }

    func testClearUsers() {
        service.addUser(id: "1", name: "Alice")
        service.addUser(id: "2", name: "Bob")
        service.clearUsers()
        XCTAssertEqual(service.getUserCount(), 0)
    }

    func testGetNonExistentUser() {
        XCTAssertNil(service.getUser(id: "nonexistent"))
    }
}
