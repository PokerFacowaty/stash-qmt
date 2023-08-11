import sys
import requests
from PySide6.QtWidgets import (QApplication, QPushButton, QLineEdit, QDialog,
                               QVBoxLayout, QLabel, QComboBox, QCheckBox)
from PySide6.QtCore import Slot
from pathlib import Path
import yaml

API_KEY = ""
STASH_URL = ""
TEMPLATES = {}


def parse_yaml() -> None:
    '''Retrieves info from the config.yaml file, creates it with basic info if
       it doesn't exist. Calls get_tag_ids() to fetch ids for lists of tag
       names. Saves all the data back to the file so that lists of tag names
       become dicts of tag ids and their names.'''

    global API_KEY
    global STASH_URL
    global TEMPLATES
    fpath = Path(__file__).parent.resolve() / "config.yaml"

    if fpath.exists():
        with open(fpath, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    else:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write("# Find the docs at github.com/PokerFacowaty/stash-qmt\n"
                    + "API Key:\nStashURL:\nTemplates:")
        raise FileNotFoundError("config.yaml was not found, created it now")

    API_KEY = cfg["API Key"]
    STASH_URL = cfg["Stash URL"]

    for tmpl in cfg["Templates"]:
        if isinstance(cfg["Templates"][tmpl], dict):
            TEMPLATES[tmpl] = cfg["Templates"][tmpl]
        elif isinstance(cfg["Templates"][tmpl], list):
            ids_tags = get_tag_ids(cfg["Templates"][tmpl])
            cfg["Templates"][tmpl] = ids_tags
            TEMPLATES[tmpl] = ids_tags
        else:
            print(f"Template format not recognized for {tmpl}, skipping...")

    with open(fpath, "w", encoding="utf-8") as f:
        f.write("# Find the docs at github.com/PokerFacowaty/stash-qmt\n")
        yaml.safe_dump({"API Key": API_KEY}, f)
        yaml.safe_dump({"Stash URL": STASH_URL}, f)
        yaml.safe_dump({"Templates": TEMPLATES}, f)


def get_tag_ids(tags: list) -> dict:
    '''Makes an API call to retrieve ids for tags from their names.'''

    result = {}

    for tag_name in tags:
        tag_id = ""
        query = ('{ findTags(filter: {q: "'
                 + tag_name
                 + '", per_page: -1})'
                 + '{count\ntags{id name}}}')
        r = requests.post(STASH_URL,
                          json={"query": query},
                          headers={"Content-Type": "application/json",
                                   "ApiKey": API_KEY})
        find_tags = r.json()["data"]["findTags"]
        # If there's only one tag, then it has to be the one we're looking for,
        # in case of more we're looping through them to find the exact match.
        if find_tags["count"] == 1:
            tag_id = find_tags["tags"][0]["id"]
        else:
            for tag in find_tags["tags"]:
                if tag["name"] == tag_name:
                    tag_id = tag["id"]
                    break
        result[int(tag_id)] = tag_name
    return result


class Form(QDialog):

    def __init__(self, parent=None) -> None:
        super(Form, self).__init__(parent)

        templates_id = QLabel("Select Template:")
        self.template_box = QComboBox()
        id_label = QLabel("Scene ID:")
        self.id_edit = QLineEdit()
        get_scene_button = QPushButton("Get Scene")
        set_tags_button = QPushButton("Set tags")

        self.layout = QVBoxLayout()

        self.layout.addWidget(templates_id)
        self.layout.addWidget(self.template_box)
        self.layout.addWidget(id_label)
        self.layout.addWidget(self.id_edit)
        self.layout.addWidget(get_scene_button)
        self.template_box.addItems([x for x in TEMPLATES.keys()])
        self.layout.addWidget(set_tags_button)
        self.layout.addStretch(1)

        self.setLayout(self.layout)

        get_scene_button.clicked.connect(self.add_checkboxes)
        set_tags_button.clicked.connect(self.send_tags)

    @Slot()
    def add_checkboxes(self) -> None:
        '''Retrieves necessary data from other functions and then adds
           checkboxes based on it.'''

        self.cleanup(self.layout)
        self.checkboxes = []
        self.scene_tags_ids = self.get_scene_tags_ids(self.id_edit.text())
        tags_for_checkboxes = self.filter_out_ids(self.template_box,
                                                  self.scene_tags_ids)
        tags_for_checkboxes = sorted(tags_for_checkboxes.items(),
                                     key=lambda x: x[1], reverse=True)

        for k, v in tags_for_checkboxes:
            check = QCheckBox()
            check.setText(v)
            self.checkboxes.append((k, check))
            self.layout.insertWidget(5, check)

    @staticmethod
    def get_scene_tags_ids(scene_id: str) -> dict:
        '''Makes an API call to retrieve tag ids from the chosen scene and puts
           them as keys in a dict for fast lookups later on.'''

        query = ('{findScene(id: '
                 + scene_id
                 + ') {tags {id}}}')
        r = requests.post(STASH_URL,
                          json={"query": query},
                          headers={"Content-Type": "application/json",
                                   "ApiKey": API_KEY})
        current_scene_tag_ids = {int(x["id"]): True for x
                                 in r.json()["data"]["findScene"]["tags"]}
        return current_scene_tag_ids

    @staticmethod
    def cleanup(layout) -> None:
        '''Cleans up the layout - removes the checkboxes as well as the
           success message label at the bottom.'''

        index = layout.count()
        index -= 1
        if isinstance(layout.itemAt(index).widget(), QLabel):
            layout.itemAt(index).widget().setParent(None)
            index -= 1
        while (index >= 0):
            if isinstance(layout.itemAt(index).widget(), QCheckBox):
                widg = layout.itemAt(index).widget()
                widg.setParent(None)
            index -= 1

    @staticmethod
    def filter_out_ids(template_box, scene_tags_ids):
        '''Filters out tag ids that are already present in the scene so that
           they're not shown on the GUI.'''

        current_template = template_box.currentText()
        tags_for_checkboxes = {}
        for id_ in TEMPLATES[current_template].keys():
            if not scene_tags_ids.get(id_, False):
                tags_for_checkboxes[id_] = TEMPLATES[current_template][id_]
        return tags_for_checkboxes

    @Slot()
    def send_tags(self):
        tags_to_send = [x for x in self.scene_tags_ids.keys()]
        for k, chbox in self.checkboxes:
            if chbox.isChecked():
                tags_to_send.append(k)
        scene_id = self.id_edit.text()
        query = ('mutation {\n sceneUpdate(input: {id: '
                 + str(scene_id)
                 + ', tag_ids: '
                 + str(tags_to_send)
                 + '}){id}}')
        r = requests.post(STASH_URL,
                          json={"query": query},
                          headers={"Content-Type": "application/json",
                                   "ApiKey": API_KEY})
        if r.ok:
            self.layout.addWidget(QLabel("Tags added succesfully!"))


if __name__ == "__main__":
    parse_yaml()
    app = QApplication(sys.argv)
    form = Form()
    form.show()
    sys.exit(app.exec())
