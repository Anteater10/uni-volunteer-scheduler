---
phase: 05
plan: 06
name: "Preview UI — admin import page with polling, editable rows"
wave: 3
depends_on: ["05-03", "05-05"]
files_modified:
  - frontend/src/pages/AdminImportPage.jsx
  - frontend/src/components/ImportPreviewTable.jsx
  - frontend/src/components/ImportUploadForm.jsx
  - frontend/src/lib/api.js
  - frontend/src/App.jsx
autonomous: true
requirements:
  - "preview UI with row-level validation"
  - "`_confidence` field"
  - "Stage 2 deterministic importer (schema validation, conflict detection, atomic commit with rollback)"
---

# Plan 05-06: Preview UI — Admin Import Page with Polling, Editable Rows

<objective>
Build the `/admin/import` frontend page. Users upload a CSV, see a progress indicator
while the Celery task processes, then see a preview table. Low-confidence rows are
highlighted in amber with inline editing. The "Commit" button is disabled while any
low-confidence row remains unresolved. On commit, display success count or error details.
</objective>

<must_haves>
- `/admin/import` route renders `AdminImportPage`
- CSV upload form with drag-and-drop or file picker, restricted to `.csv`
- Upload calls `POST /admin/imports` and receives `import_id`
- Frontend polls `GET /admin/imports/{id}` every 2 seconds until status is `ready` or `failed`
- Preview table shows columns: Row #, Module, Location, Start, End, Capacity, Instructor, Status, Actions
- Rows with status `low_confidence` highlighted in amber background
- Rows with status `conflict` highlighted in red background
- Rows with status `ok` have green indicator
- Inline edit: clicking Edit on a row makes module, location, capacity, instructor fields editable
- Save edit calls `PATCH /admin/imports/{id}/rows/{index}` with changed fields
- Summary bar: "N events to create, M to review, K conflicts"
- "Commit All" button disabled while `to_review > 0`
- Commit calls `POST /admin/imports/{id}/commit`
- On success: display green banner "Created N events successfully"
- On failure: display red error banner with failing row index and reason
- Loading skeleton while polling
</must_haves>

<tasks>

<task id="05-06-01" parallel="false">
<read_first>
- frontend/src/lib/api.js
</read_first>
<action>
Edit `frontend/src/lib/api.js` — add import API functions:

```javascript
// --- CSV Imports ---
export const uploadCsvImport = (file) => {
  const formData = new FormData();
  formData.append("file", file);
  return api.post("/admin/imports", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then(r => r.data);
};
export const getCsvImport = (importId) => api.get(`/admin/imports/${importId}`).then(r => r.data);
export const updateImportRow = (importId, rowIndex, data) =>
  api.patch(`/admin/imports/${importId}/rows/${rowIndex}`, data).then(r => r.data);
export const commitCsvImport = (importId) => api.post(`/admin/imports/${importId}/commit`).then(r => r.data);
```
</action>
<acceptance_criteria>
- `grep "uploadCsvImport" frontend/src/lib/api.js` returns a match
- `grep "getCsvImport" frontend/src/lib/api.js` returns a match
- `grep "updateImportRow" frontend/src/lib/api.js` returns a match
- `grep "commitCsvImport" frontend/src/lib/api.js` returns a match
- `grep "multipart/form-data" frontend/src/lib/api.js` returns a match
</acceptance_criteria>
</task>

<task id="05-06-02" parallel="false">
<read_first>
- frontend/src/pages/AdminDashboardPage.jsx (for layout patterns)
- frontend/src/components/ (list existing components for reuse)
</read_first>
<action>
Create `frontend/src/components/ImportUploadForm.jsx`:

Build a component that:
- Renders a file input restricted to `.csv` (`accept=".csv"`)
- Has a drag-and-drop zone with visual feedback (dashed border, highlight on drag)
- On file select/drop, calls `onUpload(file)` prop
- Shows "Uploading..." state while parent processes
- Validates file extension client-side before calling onUpload
- Uses Tailwind classes for styling: `border-2 border-dashed border-gray-300 rounded-lg p-8 text-center`
- Drag-over state: `border-blue-500 bg-blue-50`
</action>
<acceptance_criteria>
- `test -f frontend/src/components/ImportUploadForm.jsx` exits 0
- `grep "accept.*csv" frontend/src/components/ImportUploadForm.jsx` returns a match (case insensitive)
- `grep "onUpload\|onDrop\|drag" frontend/src/components/ImportUploadForm.jsx` returns a match
- `grep "border-dashed" frontend/src/components/ImportUploadForm.jsx` returns a match
</acceptance_criteria>
</task>

<task id="05-06-03" parallel="false">
<read_first>
- frontend/src/pages/AdminDashboardPage.jsx
</read_first>
<action>
Create `frontend/src/components/ImportPreviewTable.jsx`:

Build a component that receives `preview` prop (the ImportPreview payload) and renders:
- Summary bar at top: "{to_create} to create | {to_review} to review | {conflicts} conflicts"
- Table with columns: #, Module, Location, Start, End, Capacity, Instructor, Status, Actions
- Row coloring based on status:
  - `ok` rows: `bg-green-50` left border
  - `low_confidence` rows: `bg-amber-50` with amber left border
  - `conflict` rows: `bg-red-50` with red left border
- Each row has an "Edit" button. When clicked, fields (module_slug, location, capacity, instructor_name) become input fields.
- "Save" button on edited row calls `onSaveRow(index, updatedFields)`
- "Cancel" button reverts to read-only
- Warnings displayed as tooltips or inline text under each row
- "Commit All" button at bottom:
  - Disabled with tooltip "Resolve all flagged rows first" when `to_review > 0`
  - Enabled and green (`bg-green-600 text-white`) when all rows resolved
  - Calls `onCommit()` prop
</action>
<acceptance_criteria>
- `test -f frontend/src/components/ImportPreviewTable.jsx` exits 0
- `grep "bg-amber-50\|amber" frontend/src/components/ImportPreviewTable.jsx` returns a match
- `grep "bg-red-50\|red" frontend/src/components/ImportPreviewTable.jsx` returns a match
- `grep "bg-green" frontend/src/components/ImportPreviewTable.jsx` returns a match
- `grep "Commit\|commit" frontend/src/components/ImportPreviewTable.jsx` returns a match
- `grep "disabled\|Disabled" frontend/src/components/ImportPreviewTable.jsx` returns a match
- `grep "onSaveRow\|onCommit" frontend/src/components/ImportPreviewTable.jsx` returns a match
</acceptance_criteria>
</task>

<task id="05-06-04" parallel="false">
<read_first>
- frontend/src/pages/AdminDashboardPage.jsx
- frontend/src/components/ImportUploadForm.jsx (after task 02)
- frontend/src/components/ImportPreviewTable.jsx (after task 03)
- frontend/src/lib/api.js (after task 01)
</read_first>
<action>
Create `frontend/src/pages/AdminImportPage.jsx`:

Build the page component that:
1. Initially shows `ImportUploadForm`
2. On upload: calls `uploadCsvImport(file)`, stores `importId` in state
3. Starts polling `getCsvImport(importId)` every 2 seconds using `setInterval`
4. While polling (status `pending` or `processing`): shows a loading skeleton/spinner with "Processing CSV..."
5. When status is `ready`: clears interval, renders `ImportPreviewTable` with preview data
6. When status is `failed`: clears interval, shows error message from `error_message` field
7. On row save: calls `updateImportRow(importId, index, data)`, refreshes preview
8. On commit: calls `commitCsvImport(importId)`
   - Success: shows green banner "Created {N} events successfully" + list of created events
   - Failure: shows red banner with error details
9. "Upload Another" button to reset state and show upload form again

State management:
- `importId: string | null`
- `importData: object | null`
- `isPolling: boolean`
- `commitResult: object | null`
- `error: string | null`

Cleanup: clear interval on unmount (`useEffect` cleanup function).
</action>
<acceptance_criteria>
- `test -f frontend/src/pages/AdminImportPage.jsx` exits 0
- `grep "AdminImportPage" frontend/src/pages/AdminImportPage.jsx` returns a match
- `grep "setInterval\|polling\|2000" frontend/src/pages/AdminImportPage.jsx` returns a match
- `grep "uploadCsvImport\|getCsvImport\|commitCsvImport" frontend/src/pages/AdminImportPage.jsx` returns a match
- `grep "ImportUploadForm\|ImportPreviewTable" frontend/src/pages/AdminImportPage.jsx` returns a match
- `grep "Processing\|processing" frontend/src/pages/AdminImportPage.jsx` returns a match
- `grep "clearInterval\|useEffect" frontend/src/pages/AdminImportPage.jsx` returns a match
</acceptance_criteria>
</task>

<task id="05-06-05" parallel="false">
<read_first>
- frontend/src/App.jsx
</read_first>
<action>
Edit `frontend/src/App.jsx`:

1. Import `AdminImportPage`:
   ```javascript
   import AdminImportPage from "./pages/AdminImportPage";
   ```

2. Add route inside the admin routes section:
   ```jsx
   <Route path="/admin/import" element={<AdminImportPage />} />
   ```

3. If an admin navigation/sidebar exists, add "CSV Import" link pointing to `/admin/import`.
</action>
<acceptance_criteria>
- `grep "AdminImportPage" frontend/src/App.jsx` returns a match
- `grep "admin/import" frontend/src/App.jsx` returns a match
</acceptance_criteria>
</task>

</tasks>

<verification>
- `/admin/import` route loads the page without errors
- File upload form accepts `.csv` files only
- Polling displays loading state then preview table
- Low-confidence rows are visually highlighted in amber
- Conflict rows are visually highlighted in red
- Inline edit works and calls PATCH endpoint
- Commit button is disabled when unresolved rows exist
- Commit success shows green banner with count
- No polling interval leaks (cleanup on unmount)
</verification>

<threat_model>
- **Client-side file type bypass:** Frontend validates `.csv` extension, but backend also validates. Defense in depth.
- **Polling interval leak:** `useEffect` cleanup function clears the polling interval. No resource leak on navigation.
- **XSS in preview data:** React auto-escapes JSX content. Raw CSV data displayed in table cells is safe from XSS.
- **CSRF on commit:** Existing auth token (bearer JWT) protects all API calls. No CSRF risk.
</threat_model>
