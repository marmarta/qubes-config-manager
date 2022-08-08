# Clickable URLs

To add a label with a URL that's to be opened in the default dispvm, 
add it's label to `_handle_urls`.

# Policy Handlers

The generic class PolicyHandlers allows for handling of simple policy files,
with some variability for rules where we want to set target vm, or 
target= and default_target params.

## Widget naming convention

Every instance of PolicyHandler has its own prefix.
The following widgets are required:

- Gtk.ListBox `{prefix}_main_list` that will contain fundamental rules
- Gtk.ListBox `{prefix}_exception_list` that will contain exceptions to the rules
- Gtk.Button `{prefix}_add_rule_button` for the add new rule button
- Gtk.EventBox `{prefix}_raw_event` for the eventbox for clickable raw rule expander
- Gtk.Box `{prefix}_raw_box` box containing widgets with raw rule text
- Gtk.Image `{prefix}_raw_expander` Image for the expanding triangle icon
- Gtk.TextView `{prefix}_raw_text` raw text of the rule
- Gtk.Button `{prefix}_raw_save` button for saving the raw rule text changes
- Gtk.Button `{prefix}_raw_cancel` button for cancelling the raw rule text changes
- Gtk.RadioButton `{prefix}_enable_radio` RadioButton to enable custom policy changes
- Gtk.RadioButton `{prefix}_disable_radio` RadioButton to set default policy
- Gtk.Box `{prefix}_problem_box` box with information about conflicting policy files
- Gtk.ListBox `{prefix}_problem_files_list` list of conflicting policy files
