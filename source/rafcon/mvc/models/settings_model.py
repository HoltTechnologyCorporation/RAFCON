"""
.. module:: settings_model
   :platform: Unix, Windows
   :synopsis: a module which manages the configuration settings GUI

.. moduleauthor:: Benno Voggenreiter

"""
from gtkmvc import ModelMT
from rafcon.utils import log
import yaml

from rafcon.mvc.config import global_gui_config
from rafcon.statemachine.config import global_config

logger = log.get_logger(__name__)


class SettingsModel(ModelMT):
    """
    Model which manages the configuration settings GUI
    """
    config_list = []
    config_gui_list = []
    config_library_list = []
    config_shortcut_list = []
    __observables__ = ["config_list", "config_gui_list", "config_library_list", "config_shortcut_list", ]

    def __init__(self, config_list=None, config_gui_list=None, config_library_list=None,
                 config_shortcut_list=None, dialog_flag=None, meta=None):
        ModelMT.__init__(self)
        self.config_list = config_list if config_list else []
        self.config_gui_list = config_gui_list if config_gui_list else []
        self.config_library_list = config_library_list if config_library_list else []
        self.config_shortcut_list = config_shortcut_list if config_shortcut_list else []
        default_config_dict = yaml.load(global_config.default_config)
        self.config_dict = {k for k in default_config_dict.keys() if k not in ["LIBRARY_PATHS", "TYPE"]}
        default_gui_config_dict = yaml.load(global_gui_config.default_config)
        self.gui_config_dict = {k for k in default_gui_config_dict.keys() if k not in ["SHORTCUTS", "TYPE"]}
        self.changed_keys = {}
        self.change_by_restart = []
        self.register_observer(self)
        # {key:(changed, refresh_sm, restart)
        self.checkup_dict = {'GAPHAS_EDITOR': [False, True, False],
                             'MAX_VISIBLE_LIBRARY_HIERARCHY': [False, True, False],
                             'HISTORY_ENABLED': [False, True, False],
                             'AUTO_BACKUP_ENABLED': [False, True, False],
                             'AUTO_BACKUP_ONLY_FIX_FORCED_INTERVAL': [False, True, False],
                             'AUTO_BACKUP_FORCED_STORAGE_INTERVAL': [False, True, False],
                             'AUTO_BACKUP_DYNAMIC_STORAGE_INTERVAL': [False, True, False],
                             'AUTO_RECOVERY_CHECK': [False, True, False],
                             'AUTO_RECOVERY_LOCK_ENABLED': [False, True, False],
                             'USE_ICONS_AS_TAB_LABELS': [False, False, True]
                             #'SOURCE_EDITOR_STYLE': [False, True, False]
                             }

        self.checkval = [False, False, False]

    def get_settings(self):
        """
        A function to get all values of settings listed in the dicts
        :return:
        """
        del self.config_list[:]
        for key in sorted(self.config_dict):
            if global_config.get_config_value(key) is not None:
                self.config_list.append((key, global_config.get_config_value(key)))

        del self.config_library_list[:]
        library_dict = global_config.get_config_value('LIBRARY_PATHS')
        if library_dict is not None:
            for key in sorted(library_dict.keys()):
                self.config_library_list.append((key, library_dict[key]))

        del self.config_gui_list[:]
        for key in sorted(self.gui_config_dict):
            if global_gui_config.get_config_value(key) is not None:
                self.config_gui_list.append((key, global_gui_config.get_config_value(key)))

        del self.config_shortcut_list[:]
        shortcut_dict = global_gui_config.get_config_value('SHORTCUTS')
        if shortcut_dict is not None:
            for key in sorted(shortcut_dict.keys()):
                self.config_shortcut_list.append((key, shortcut_dict[key]))

    def set_config_view_value(self, key, value, list_nr):
        """
        A method to set all config values into the config.yaml
        :param key: setting which changed
        :param value: new value for a config which shall be updated
        :param list_nr: number to select the correct list, which needs to be updated
        :return
        """
        if list_nr == 0:
            actual_list = self.config_list
        elif list_nr == 1:
            actual_list = self.config_gui_list
        elif list_nr == 2:
            actual_list = self.config_shortcut_list
            value = [value[2:-2]]
        else:
            actual_list = self.config_library_list
        for key_pair in actual_list:
            if key == key_pair[0]:
                index = actual_list.index(key_pair)
                actual_list.remove(key_pair)
                actual_list.insert(index, (key, value))
                self.changed_keys[key] = value
                if key in self.checkup_dict:
                    self.checkup_dict[key][0] = True

    def save_and_apply_config(self):
        from rafcon.mvc.singleton import main_window_controller
        for key in self.changed_keys:
            if key not in self.checkup_dict:
                if key in self.config_dict:
                    # print "set core config, restart needed"
                    global_config.set_config_value(key, self.changed_keys[key])
                    self.checkval[2] |= True
                    if key not in self.change_by_restart:
                        self.change_by_restart.append(key)
                elif key in dict(self.config_shortcut_list):
                    # print "set shortcut"
                    global_gui_config.set_config_value("SHORTCUTS", dict(self.config_shortcut_list))
                    main_window_controller.get_controller('menu_bar_controller').refresh_shortcuts_activate()
                    # update sc
                elif key in dict(self.config_library_list):
                    # print "set library"
                    global_config.set_config_value("LIBRARY_PATHS", dict(self.config_library_list))
                    main_window_controller.get_controller('menu_bar_controller').on_refresh_libraries_activate(widget=None, data=None)
                else:
                    # print "set gui config without restart/refresh"
                    if key == "SOURCE_EDITOR_STYLE":
                        main_window_controller.get_controller('states_editor_ctrl').reload_style()
                    global_gui_config.set_config_value(key, self.changed_keys[key])
                    if "LOGGING_SHOW_" in key:
                        if "INFO" in key:
                            main_window_controller.view['button_show_info'].set_active(self.changed_keys[key])
                        elif "DEBUG" in key:
                            main_window_controller.view['button_show_debug'].set_active(self.changed_keys[key])
                        elif "WARNING" in key:
                            main_window_controller.view['button_show_warning'].set_active(self.changed_keys[key])
                        else:
                            main_window_controller.view['button_show_error'].set_active(self.changed_keys[key])
                        main_window_controller.view.logging_view.update_filtered_buffer()
            # gui setting:
            else:
                for k in self.checkup_dict:
                    # changed == True
                    if self.checkup_dict[k][0]:
                        self.checkval[1] |= self.checkup_dict[k][1]
                        self.checkval[2] |= self.checkup_dict[k][2]
                        # print "set gui config"
                        global_gui_config.set_config_value(k, self.changed_keys[k])
                        self.checkup_dict[k][0] = False
                        if self.checkup_dict[k][2] and k not in self.change_by_restart:
                            self.change_by_restart.append(key)
        if self.checkval[1]:
            # print "refresh sm"
            main_window_controller.get_controller('menu_bar_controller').on_refresh_all_activate(widget=None, data=None)
        self.checkval = [False, False, False]
        global_config.save_configuration()
        global_gui_config.save_configuration()
        self.changed_keys = {}





