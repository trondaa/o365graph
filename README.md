# o365graph
Connector for Sesam to use the Microsoft Graph Api


### Environment variables

#### Required

* client_id
* client_secret
* grant_type
* resource
* entities_path
* next_page
* token_url

#### Required if grant_type is password

* client_id
* client_secret
* username
* password
* grant_type
* resource
* scope
* entities_path
* next_page
* token_url

#### Optional

* log_level
* base_url
* sleep
* sharepoint_url


### URL routes

#### /entities/<path>
generic endpoint to return all types of entities based on the given graph url. [Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer#) is your friend.

GET request will return entities based on the given relative url

#### /file/<path>

This endpoint requires the env var 'sharepoint_url'

It uses the default document library "Shared Documents". To specify a different document library, add a section to the path after the site/team with /doclib:MyFancyDocumentLib/
i.e. `teams/SesamTeam/doclib:SpecialLib/folder2/my_awesome_file.pdf`

GET request with a *file path* will return the file bytes
GET request with a *directory path* will return metadata for all files in directory path
POST request will write file to the given file path

#### /metadata/<path>

This endpoint requires the env var 'sharepoint_url'

It uses the default document library "Shared Documents". To specify a different document library, add a section to the path after the site/team with /doclib:MyFancyDocumentLib/
i.e. `teams/SesamTeam/doclib:SpecialLib/folder2/my_awesome_file.pdf`

POST request writes metadata to the given document file path (Managed metadata currently not supported)
Payload must be in the following format:
```json
{
  "my_column": "Some value"
}
```

#### /user-image/<path>

Specify image upload location in path. The path needs to contain placeholder `{user}` which will be replaced by user ID or UPN from payload attribute "user" i.e. `/user-image/users/{user}/photo/$value`

Payload must contain the following:
```json
{
  "user": "O365 user id or userPrincipalName",
  "image": "base64 encoded image data"
}
```
#### /upsert/<path>

Insert or update entities depending on if a property named id is present or not. The path determines where to do the insert/update i.e. `/termStore/groups/<term group id>/sets/<term set id>/terms/`

Payload must contain the following to be updated:
```json
{
  "id": "<id of the entity to be updated>",
  "property": "<property to update>"
}
```

Payload must not contain the property `id` to be inserted:
```json
{
  "property": "<property to insert>"
}
```
