# TA-notableeditor
This app provides a custom search command to mass edit notable events

## Example
```
`notable` | head 10 | editnotables comment="some_comment" status="new" urgency="informational" newOwner="admin" disposition="Other"
```
```
`notable`
| eval notable_edit_disposition="True Positive - Suspicious Activity", notable_edit_status="closed", notable_edit_urgency="low", notable_edit_newOwner="admin", notable_edit_comment="asd"
| editnotables mode=single
```
