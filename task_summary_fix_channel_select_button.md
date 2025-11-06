The core task is to implement dynamic validation for the channel selection feature, as the required number of channels differs based on the data source and file structure. This involves a coordinated change between the Python backend and the JavaScript frontend. First, the backend Flask endpoint `/get-channels` in `NIDRA/nidra_gui/app.py` must be modified to not only extract channel names but also determine the recording type. It will receive the `data_source` from the frontend and, for ZMax recordings, inspect the specified directory to see if it contains a single `.edf` file or a pair of `L.edf`/`R.edf` files. Based on this analysis, it will return a `selection_mode` string ('psg', 'zmax_one_file', or 'zmax_two_files') in its JSON response, alongside the list of channels. The modified endpoint will look something like this:

```python
@app.route('/get-channels', methods=['POST'])
def get_channels():
    data = request.json
    input_path_str = data.get('input_dir')
    data_source = data.get('data_source') # New: get data_source from frontend

    # ... (logic to find search_dir from input_path_str) ...

    scorer_type = 'psg' if data_source == TEXTS["DATA_SOURCE_PSG"] else 'forehead'
    selection_mode = 'psg' # Default for PSG

    if scorer_type == 'forehead':
        l_files = list(search_dir.glob('*[lL].edf'))
        r_files = list(search_dir.glob('*[rR].edf'))
        all_edfs = list(search_dir.glob('*.edf')) + list(search_dir.glob('*.EDF'))

        if len(l_files) == 1 and len(r_files) == 1:
            selection_mode = 'zmax_two_files'
            # For two-file mode, only read channels from one file
            raw = mne.io.read_raw_edf(l_files[0], preload=False, verbose=False)
            channels = raw.ch_names
        elif len(all_edfs) == 1:
            selection_mode = 'zmax_one_file'
            raw = mne.io.read_raw_edf(all_edfs[0], preload=False, verbose=False)
            channels = raw.ch_names
        else:
            # Handle cases with no files or ambiguous files
            return jsonify({'status': 'error', 'message': f'Could not determine ZMax recording type in {search_dir}. Found {len(all_edfs)} EDF files.'}), 404
    else: # For PSG, read the first available EDF
        edf_files = list(search_dir.rglob('*.edf')) + list(search_dir.rglob('*.EDF'))
        if not edf_files:
            return jsonify({'status': 'error', 'message': f'No EDF files found in {search_dir}.'}), 404
        raw = mne.io.read_raw_edf(edf_files[0], preload=False, verbose=False)
        channels = raw.ch_names

    return jsonify({'status': 'success', 'channels': channels, 'selection_mode': selection_mode})```

Concurrently, the frontend code in `NIDRA/nidra_gui/neutralino/resources/static/script.js` must be updated. The event listener for the "Select channels" button will be modified to include the `data_source` in its `fetch` request to `/get-channels`. The `openChannelSelectionModal` function will then receive the `selection_mode` from the backend's response. Inside the modal, a message will be displayed to the user indicating the selection requirement (e.g., "Please select exactly 2 channels"). Finally, the "OK" button's event listener within the modal will enforce this rule, checking the number of selected checkboxes against the `selection_mode` before allowing the modal to close. An alert will be shown if the user's selection is invalid. The validation logic in JavaScript would be similar to this:

```javascript
// In the 'confirm-channels-btn' click listener
const selectedCheckboxes = Array.from(channelList.querySelectorAll('input[type="checkbox"]:checked'));
const selectedCount = selectedCheckboxes.length;

let isValid = false;
let message = '';

switch (currentSelectionMode) { // 'currentSelectionMode' is stored when modal opens
    case 'zmax_one_file':
        isValid = (selectedCount === 2);
        if (!isValid) message = 'Please select exactly two channels for a single-file ZMax recording.';
        break;
    case 'zmax_two_files':
        isValid = (selectedCount === 1);
        if (!isValid) message = 'Please select exactly one channel for a two-file ZMax recording.';
        break;
    case 'psg':
    default:
        isValid = true; // Any number of channels is valid for PSG
        break;
}

if (!isValid) {
    alert(message);
    return; // Prevent modal from closing
}

// If valid, proceed to save the selected channels and close the modal
selectedChannels = selectedCheckboxes.map(cb => cb.value);
channelSelectionModal.style.display = 'none';