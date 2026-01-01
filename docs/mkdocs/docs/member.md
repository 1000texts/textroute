A unique member ID is generated in the members table based on the combination of an SMS inbound/outbound number and an individual’s phone number. This design allows a single person to belong to multiple “groups.”

In TextRoute, each SMS inbound/outbound number represents a distinct group that TextRoute manages.

Example
John Doe can belong to multiple groups because he interacts with different SMS numbers:

Group 1 – Church Congregation
Person: John Doe
Phone number: 207-346-7870
SMS inbound/outbound number: 888-111-1111

Group 2 – Pickleball Circle
Person: John Doe
Phone number: 207-346-7870
SMS inbound/outbound number: 888-222-2222

Although John’s personal phone number is the same in both cases, each pairing with a different SMS number results in a different member ID, allowing TextRoute to manage membership, messaging, and permissions separately for each group.