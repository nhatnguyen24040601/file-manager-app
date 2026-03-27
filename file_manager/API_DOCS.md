# Enterprise File Manager v2 - API Documentation

This document explains how to interact with the fully completed File Manager API. It covers navigating the folder hierarchy, managing files (CRUD), moving items, and configuring advanced bitmask-based permissions.

---

## 1. Navigating Folders & Files (READ)

### Get Folder Details & Breadcrumbs
Retrieves a folder's metadata, its subfolders, files, and its breadcrumb path from the Root folder (calculated instantly via Closure Table).

* **URL:** `/file/folders/{folder_uuid}/`
* **Method:** `GET`
* **Success Response (200 OK):**
```json
{
    "metadata": {
        "id": "5ecd4d8a-fe24-4f62-a883-0c7b2097aace",
        "name": "Projects",
        "owner": 6,
        "created_at": "2026-03-27T02:47:00Z"
    },
    "path_collection": [
        { "id": "e3369a0e-...", "name": "Root" },
        { "id": "5ecd4d8a-...", "name": "Projects" }
    ],
    "entries": {
        "folders": [
            { "id": "11111111-...", "name": "Internal", "owner": 6 }
        ],
        "files": [
            { "id": "22222222-...", "name": "Budget.pdf", "file_size": 1024, "mime_type": "application/pdf" }
        ]
    }
}
```

### Get Folder Tree (Sidebar Navigation)
Retrieves a deeply nested JSON structure representing the folder tree up to a specified depth.

* **URL:** `/file/folders/{folder_uuid}/tree/?depth=3`
* **Method:** `GET`
* **Success Response (200 OK):**
```json
{
    "id": "e3369a0e-...",
    "name": "Root",
    "type": "folder",
    "children": [
        {
            "id": "5ecd4d8a-...",
            "name": "Projects",
            "type": "folder",
            "children": []
        }
    ]
}
```

---

## 2. Managing Objects (CREATE, UPDATE, DELETE)

*Folders and Files share the same base structure (`SecurableObject`), meaning renaming, moving, and deleting are completely unified endpoints!*

### Create a Folder
* **URL:** `/file/folders/`
* **Method:** `POST`
* **Body:**
```json
{
    "name": "New Project Workspace",
    "parent_id": "5ecd4d8a-fe24-4f62-a883-0c7b2097aace"
}
```

### Create a File (Metadata)
Creates the file record and automatically connects it to the Closure Table hierarchy.
* **URL:** `/file/files/`
* **Method:** `POST`
* **Body:**
```json
{
    "name": "Financial_Report_Q1.pdf",
    "parent_id": "5ecd4d8a-fe24-4f62-a883-0c7b2097aace",
    "file_size": 2048500,
    "mime_type": "application/pdf",
    "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

### Rename a Folder or File (UPDATE)
Updates the human-readable text name tied to the File/Folder.
* **URL:** `/file/objects/{object_uuid}/rename/`
* **Method:** `PATCH`
* **Body:**
```json
{
    "name": "Archived Ideas.txt"
}
```

### Move a Folder or File (UPDATE)
Securely moves an item (and all of its children if it's a folder) to a new parent folder, automatically recalculating the entire `ObjectPath` hierarchy.
* **URL:** `/file/objects/{object_uuid}/move/`
* **Method:** `PATCH`
* **Body:**
```json
{
    "new_parent_id": "e3369a0e-299d-42ad-bab2-67c404984a09"
}
```

### Soft-Delete a Folder or File (REMOVE / DELETE)
Performs an Enterprise "Soft Delete" by stamping `deleted_at = timezone.now()` on the base object. It remains in the database for auditing and recovery but disappears from normal views.
* **URL:** `/file/objects/{object_uuid}/`
* **Method:** `DELETE`
* **Success Response (204 No Content):** `(Empty Body - Deleted successfully)`

---

## 3. Dealing with Permissions (ACLs)

> **Important Note**: Files and Folders use the exact same endpoint for permissions. Also, Users and Groups use the exact same endpoint! You simply switch the UUID and specify whether it is a `"user"` or `"group"`.

The permission system uses integer bitmasks to allow multiple rights to be grouped into a single number.

### Bitmask Reference Table:
| Bit Value | Constant | Action Description |
| :--- | :--- | :--- |
| `1` | `READ_DATA` | View file content or list folder entries. |
| `2` | `WRITE_DATA` | Edit file content or rename objects. |
| `4` | `APPEND_DATA` | Add data to the end of a file. |
| `8` | `CREATE` | Create new files/folders inside a folder. |
| `16` | `DELETE` | Delete the object itself. |
| `32` | `DELETE_CHILD` | Delete any child item, even if not owned. |
| `64` | `READ_ACL` | View the permission list (who has access). |
| `128` | `WRITE_ACL` | Change permissions for other users. |
| `256` | `TRAVERSE` | Pass through a folder to reach a deeper folder. |

### Manage Permissions (Upsert, Overwrite, Remove)
* **URL:** `/file/objects/{object_uuid}/permissions/` 
*(Note: `{object_uuid}` can be either a File ID or a Folder ID)*
* **Method:** `PUT`

#### Scenario A: Give a User Read/Write Access to a File
Set `principal_type` to `"user"`, and target the File's UUID.
* **Body:**
```json
{
    "opType": 1,
    "permissions": [
        {
            "principal_id": "USER-UUID-HERE",
            "principal_type": "user",
            "allow_mask": 3,
            "deny_mask": 0,
            "inheritance_flags": "fd"
        }
    ]
}
```

#### Scenario B: Give a Group Access to a Folder
Set `principal_type` to `"group"`, and target the Folder's UUID.
* **Body:**
```json
{
    "opType": 1,
    "permissions": [
        {
            "principal_id": "GROUP-UUID-HERE",
            "principal_type": "group",
            "allow_mask": 255,   
            "deny_mask": 0,
            "inheritance_flags": "fd"
        }
    ]
}
```

---

## 4. Identity & Group Management

To fully support the ACL system, you need to map users to bits of permissions and group them together logically.

### List All Users
Retrieves a list of all active users in the system.
* **URL:** `/file/users/`
* **Method:** `GET`
* **Success Response (200 OK):** `[ { "id": "123e4567-e89b-...", "username": "admin", "email": "admin@example.com" } ]`

### List or Create Groups
* **URL:** `/file/groups/`
* **Method:** `GET` (List all), `POST` (Create)
* **POST Body:** `{"name": "Contractors", "parent_group": null}`

### Manage a Specific Group
* **URL:** `/file/groups/{group_uuid}/`
* **Method:** `GET` (Retrieve), `PATCH` (Rename/Update parent), `DELETE` (Remove Group)

### Manage Group Memberships
Add or remove users from a specific security group.

* **URL:** `/file/groups/{group_uuid}/members/`
* **Method:** `GET`
* **Success Response (200 OK):** Returns an array of User objects currently in the group.

* **Method:** `POST` (Add User to Group)
* **Body:** `{"user_id": "123e4567-e89b-..."}`

* **Method:** `DELETE` (Remove User from Group)
* **Body:** `{"user_id": "123e4567-e89b-..."}`
