import Foundation

/// User service with intentional SwiftLint issues: force_cast, redundant type annotation,
/// trailing whitespace, and style violations.

public class UserService {
    private var users: [String: String] = [:]

    public init() {}

    /// Adds a user to the service.
    /// Intentional: redundant type annotation (the type is already inferred).
    public func addUser(id: String, name: String) {
        let userId: String = id
        let userName: String = name
        users[userId] = userName
    }

    /// Gets a user by ID.
    /// Intentional: force_cast from Any to String.
    public func getUser(id: String) -> String? {
        let dict: [String: Any] = users
        guard let value = dict[id] else {
            return nil
        }
        // swiftlint:disable:next force_cast
        return value as! String
    }

    /// Returns the number of users.
    public func getUserCount() -> Int {
        return users.count
    }

    /// Clears all users from the service.
    public func clearUsers() {
        users.removeAll()
    }

    /// Checks if a user exists.
    /// Intentional: redundant type annotation on boolean.
    public func userExists(id: String) -> Bool {
        let exists: Bool = users[id] != nil
        return exists
    }

    /// Formats a greeting for a user.
    /// Intentional: force_cast usage and trailing whitespace on blank lines below.
    public func formatGreeting(id: String) -> String {
        let dict: [String: Any] = users as [String: Any]
        guard let name = dict[id] else {
            return "User not found"
        }
        let greeting: String = "Hello, \(name as! String)!"
        return greeting
    }
}
