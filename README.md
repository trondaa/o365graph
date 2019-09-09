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
