# Enterprise File Manager v2 - API Documentation

This document explains how to interact with the File Manager API. It covers navigating the folder hierarchy, managing files, and configuring advanced bitmask-based permissions.

---

## 1. Navigating Folders & Files (READ)

### Get Folder Details & Breadcrumbs
Retrieves a folder's metadata, its subfolders, files, and its breadcrumb path from the Root folder.

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

## 2. Managing Objects (Create, Update, Delete, Move)

> *Note: While the Database/Models support full CRUD via the Closure table, the specific Create/Update/Delete endpoints may need to be wired up in `views.py` using standard Django Rest Framework ViewSets. The `Move` endpoint is fully implemented.*

### Create a Folder / File
To create a file or folder, the backend assigns a parent folder and automatically generates the `ObjectPath` closure table links.

* **URL:** `/file/objects/` *(Conceptual Endpoint)*
* **Method:** `POST`
* **Body:**
```json
{
    "name": "New Project Ideas.txt",
    "type": "file",
    "parent_id": "5ecd4d8a-fe24-4f62-a883-0c7b2097aace"
}
```

### Rename an Object
* **URL:** `/file/objects/{object_uuid}/` *(Conceptual Endpoint)*
* **Method:** `PATCH`
* **Body:**
```json
{
    "name": "Archived Ideas.txt"
}
```

### Move an Object to a New Folder
This endpoint securely moves a file or folder to a new parent folder, automatically recalculating the entire `ObjectPath` hierarchy without breaking deep child relationships.

* **URL:** `/file/objects/{object_uuid}/move/`
* **Method:** `PATCH`
* **Body:**
```json
{
    "new_parent_id": "e3369a0e-299d-42ad-bab2-67c404984a09"
}
```
* **Success Response (200 OK):**
```json
{
    "status": "moved"
}
```

### Soft-Delete an Object
Sets `deleted_at` on the object. It will remain in the database but be hidden from normal API queries.
* **URL:** `/file/objects/{object_uuid}/` *(Conceptual Endpoint)*
* **Method:** `DELETE`

---

## 3. Dealing with Permissions (ACLs)

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

**Example:** To give a user `READ_DATA` (1), `WRITE_DATA` (2), and `CREATE` (8), you send `1 + 2 + 8 = 11` for the `allow_mask`.

### Get Object Permissions
Lists all users and groups that have explicit ACL entries applied to this specific file or folder.

* **URL:** `/file/objects/{object_uuid}/permissions/`
* **Method:** `GET`
* **Success Response (200 OK):**
```json
[
    {
        "id": "permission-uuid-1",
        "principal_id": "user-uuid-abc",
        "principal_type": "user",
        "allow_mask": 11,
        "deny_mask": 0,
        "inheritance_flags": "fd"
    }
]
```

### Manage Permissions (Upsert, Overwrite, Remove)
You can configure exactly how you want to alter permissions by changing the `opType`.

* **URL:** `/file/objects/{object_uuid}/permissions/`
* **Method:** `PUT`

#### Scenario A: Give a User Read/Write Access (opType: 1 = Upsert)
If the user already has permissions, this modifies them. If not, it creates a new permission row.
* **Body:**
```json
{
    "opType": 1,
    "permissions": [
        {
            "principal_id": "user-uuid-abc",
            "principal_type": "user",
            "allow_mask": 11,
            "deny_mask": 0,
            "inheritance_flags": "fd"
        }
    ]
}
```

#### Scenario B: Reset ALL Permissions for a Folder (opType: 2 = Overwrite All)
Deletes EVERY existing permission on the folder and replaces it entirely with the array provided.
* **Body:**
```json
{
    "opType": 2,
    "permissions": [
        {
            "principal_id": "group-uuid-managers",
            "principal_type": "group",
            "allow_mask": 255,   // Full Access
            "deny_mask": 0,
            "inheritance_flags": "fd"
        }
    ]
}
```

#### Scenario C: Remove a Specific User's Permissions (opType: 3 = Remove)
Revokes all explicit permissions for the listed user(s) on this object.
* **Body:**
```json
{
    "opType": 3,
    "permissions": [
        {
            "principal_id": "user-uuid-abc",
            "principal_type": "user"
        }
    ]
}
```
* **Success Response (200 OK):** Returns the updated array of permissions currently active on the object.
