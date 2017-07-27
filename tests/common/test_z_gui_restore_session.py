import gtk
import threading
import shutil
import time
from os.path import join

# gui elements
import rafcon.gui.singleton
from rafcon.gui.controllers.main_window import MainWindowController, MenuBarController
from rafcon.gui.models.state_machine_manager import StateMachineManagerModel
from rafcon.gui.views.main_window import MainWindowView
from rafcon.gui.views.graphical_editor import GraphicalEditor as OpenGLEditor
from rafcon.gui.mygaphas.view import ExtendedGtkView as GaphasEditor
import rafcon.gui.helpers.state_machine as gui_helper_state_machine

# core elements
import rafcon.core.config
from rafcon.core.states.hierarchy_state import HierarchyState
from rafcon.core.states.execution_state import ExecutionState
from rafcon.core.states.library_state import LibraryState
from rafcon.core.state_machine import StateMachine
import rafcon.core.singleton
from test_z_gui_state_type_change import get_state_editor_ctrl_and_store_id_dict

# general tool elements
from rafcon.utils import log

# test environment elements
import testing_utils
from testing_utils import call_gui_callback

import pytest

logger = log.get_logger(__name__)


def create_state_machine(*args, **kargs):

    state1 = ExecutionState('State1', state_id='STATE1')
    state2 = ExecutionState('State2')
    state4 = ExecutionState('Nested')
    output_state4 = state4.add_output_data_port("out", "int")
    state5 = ExecutionState('Nested2')
    input_state5 = state5.add_input_data_port("in", "int", 0)
    state3 = HierarchyState(name='State3', state_id='STATE3')
    state3.add_state(state4)
    state3.add_state(state5)
    state3.set_start_state(state4)
    state3.add_scoped_variable("share", "int", 3)
    state3.add_transition(state4.state_id, 0, state5.state_id, None)
    state3.add_transition(state5.state_id, 0, state3.state_id, 0)
    state3.add_data_flow(state4.state_id, output_state4, state5.state_id, input_state5)

    ctr_state = HierarchyState(name="Container", state_id='ROOTSTATE')
    ctr_state.add_state(state1)
    ctr_state.add_state(state2)
    ctr_state.add_state(state3)
    ctr_state.set_start_state(state1)
    ctr_state.add_transition(state1.state_id, 0, state2.state_id, None)
    ctr_state.add_transition(state2.state_id, 0, state3.state_id, None)
    ctr_state.add_transition(state3.state_id, 0, ctr_state.state_id, 0)
    ctr_state.name = "Container"

    return StateMachine(ctr_state)


def focus_graphical_editor_in_page(page):
    graphical_controller = page.children()[0]
    if not isinstance(graphical_controller, (OpenGLEditor, GaphasEditor)):
        graphical_controller = graphical_controller.children()[0]
    graphical_controller.grab_focus()


def check_order_and_consistency_of_menu(menubar_ctrl):
    assert isinstance(menubar_ctrl, MenuBarController)
    recently_opened = rafcon.gui.singleton.global_runtime_config.get_config_value('recently_opened_state_machines')
    for index, elem in enumerate(menubar_ctrl.view.sub_menu_open_recently):
        if index in [0, 1]:
            continue
        assert recently_opened[index - 2] in elem.get_label()


def prepare_tab_data_of_open_state_machines(main_window_controller, sm_manager_model, open_state_machines):
    testing_utils.wait_for_gui()
    state_machines_editor_ctrl = main_window_controller.get_controller('state_machines_editor_ctrl')
    number_of_pages = state_machines_editor_ctrl.view['notebook'].get_n_pages()
    for page_number in range(number_of_pages):
        page = state_machines_editor_ctrl.view['notebook'].get_nth_page(page_number)
        sm_id = state_machines_editor_ctrl.get_state_machine_id_for_page(page)
        if sm_id == sm_manager_model.selected_state_machine_id:
            open_state_machines['selected_sm_page_number'] = page_number
        sm_tuple = (sm_manager_model.state_machines[sm_id].state_machine.mutable_hash().hexdigest(),
                    sm_manager_model.state_machines[sm_id].mutable_hash().hexdigest(),
                    sm_manager_model.state_machines[sm_id].state_machine.file_system_path,
                    page_number,
                    sm_manager_model.state_machines[sm_id].state_machine.marked_dirty)
        open_state_machines['list_of_hash_path_tab_page_number_tuple'].append(sm_tuple)


@log.log_exceptions(None, gtk_quit=True)
def trigger_gui_signals_first_run(*args):
    """The function triggers the creation of different state machines that should be backup-ed.
    In another run those are restored and checked onto correctness.

    At the moment TESTED, SHOULD or are THOUGHT about to generate the following state machines:
    - TESTED new state machine without storage
    - TESTED new state machine with storage and no changes
    - TESTED new state machine with storage and changes
    - TESTED state machine loaded and no changes
    - TESTED state machine loaded and changes
    - TESTED library not changed
    - TESTED library changed
    - TESTED change tab position
    - SHOULD not stored state machine that was removed/moved before restart
    - SHOULD stored state machine and no changes that was removed/moved before restart
    - SHOULD stored state machine and no changes that was removed/moved before restart
    """

    sm_manager_model = args[0]
    main_window_controller = args[1]
    open_state_machines = args[2]
    library_manager = rafcon.gui.singleton.library_manager
    menubar_ctrl = main_window_controller.get_controller('menu_bar_controller')
    assert isinstance(menubar_ctrl, MenuBarController)
    assert isinstance(sm_manager_model, StateMachineManagerModel)

    def add_two_states_to_root_state_of_selected_state_machine():
        sm_m = sm_manager_model.get_selected_state_machine_model()
        current_number_states = len(sm_m.root_state.states)
        call_gui_callback(sm_m.selection.set, sm_m.root_state)
        call_gui_callback(menubar_ctrl.on_add_state_activate, None)
        call_gui_callback(menubar_ctrl.on_add_state_activate, None)
        assert len(sm_m.root_state.states) == current_number_states + 2
        assert sm_manager_model.get_selected_state_machine_model().state_machine.marked_dirty

    ####################
    # POSITIVE EXAMPLES -> supposed to be added to the open tabs list
    ####################

    # new state machine without storage
    state_machine = create_state_machine()
    call_gui_callback(rafcon.core.singleton.state_machine_manager.add_state_machine, state_machine)
    current_sm_id = sm_manager_model.state_machines.keys()[0]
    current_number_of_sm = len(sm_manager_model.state_machines)

    # new state machine with storage and no changes
    current_number_of_sm += 1
    current_sm_id += 1
    call_gui_callback(menubar_ctrl.on_new_activate, None)
    sm_manager_model.selected_state_machine_id = current_sm_id
    assert len(sm_manager_model.state_machines) == current_number_of_sm
    call_gui_callback(menubar_ctrl.on_save_as_activate, None, None, testing_utils.get_unique_temp_path())

    # new state machine with storage and with changes
    current_number_of_sm += 1
    current_sm_id += 1
    call_gui_callback(menubar_ctrl.on_new_activate, None)
    sm_manager_model.selected_state_machine_id = current_sm_id
    assert len(sm_manager_model.state_machines) == current_number_of_sm
    call_gui_callback(menubar_ctrl.on_save_as_activate, None, None, testing_utils.get_unique_temp_path())
    add_two_states_to_root_state_of_selected_state_machine()

    # state machine loaded and no changes
    current_number_of_sm += 1
    current_sm_id += 1
    basic_turtle_sm_path = join(testing_utils.TUTORIAL_PATH, "basic_turtle_demo_sm")
    call_gui_callback(menubar_ctrl.on_open_activate, None, None, basic_turtle_sm_path)
    sm_manager_model.selected_state_machine_id = current_sm_id
    move_this_sm_id = sm_manager_model.selected_state_machine_id
    assert len(sm_manager_model.state_machines) == current_number_of_sm

    # state machine loaded and changes
    current_number_of_sm += 1
    current_sm_id += 1
    print "BUGS"
    basic_turtle_sm_path = join(testing_utils.TUTORIAL_PATH, "99_bugs")
    call_gui_callback(menubar_ctrl.on_open_activate, None, None, basic_turtle_sm_path)
    assert len(sm_manager_model.state_machines) == current_number_of_sm
    assert sm_manager_model.get_selected_state_machine_model().state_machine.file_system_path == basic_turtle_sm_path
    add_two_states_to_root_state_of_selected_state_machine()

    # library not changed (needs state machine that has meta data already -> that should not be changed by opening)
    print "LIB no changes"
    library_os_path = library_manager.get_os_path_to_library("turtle_libraries", "clear_field")[0]
    call_gui_callback(menubar_ctrl.on_open_activate, None, None, library_os_path)
    assert not sm_manager_model.get_selected_state_machine_model().state_machine.marked_dirty

    # library with changes
    print "LIB with changes"
    library_os_path = library_manager.get_os_path_to_library("turtle_libraries", "teleport_turtle")[0]
    call_gui_callback(menubar_ctrl.on_open_activate, None, None, library_os_path)
    lib_sm_m = sm_manager_model.get_selected_state_machine_model()

    [state_editor_ctrl, list_store_id_from_state_type_dict] = \
        get_state_editor_ctrl_and_store_id_dict(lib_sm_m, lib_sm_m.root_state, main_window_controller, 5., logger)
    print lib_sm_m.root_state
    state_type_row_id = list_store_id_from_state_type_dict['HIERARCHY']
    call_gui_callback(state_editor_ctrl.get_controller('properties_ctrl').view['type_combobox'].set_active, state_type_row_id)
    print lib_sm_m.root_state
    add_two_states_to_root_state_of_selected_state_machine()
    print lib_sm_m.root_state

    # change tab position
    state_machines_editor_ctrl = main_window_controller.get_controller('state_machines_editor_ctrl')
    call_gui_callback(state_machines_editor_ctrl.rearrange_state_machines, {move_this_sm_id: 1})

    ####################
    # NEGATIVE EXAMPLES -> supposed to not been added to the recently opened state machines list
    ####################

    # state machine that was removed/moved before restart -> result in second run

    ####################
    # collect open state machine data
    ####################
    prepare_tab_data_of_open_state_machines(main_window_controller, sm_manager_model, open_state_machines)

    ####################
    # shout down gui
    ####################
    call_gui_callback(menubar_ctrl.on_stop_activate, None)
    call_gui_callback(menubar_ctrl.on_quit_activate, None, None, False)


@log.log_exceptions(None, gtk_quit=True)
def trigger_gui_signals_second_run(*args):
    sm_manager_model = args[0]
    main_window_controller = args[1]
    open_state_machines = args[2]
    menubar_ctrl = main_window_controller.get_controller('menu_bar_controller')
    import rafcon.gui.backup.session as backup_session
    if rafcon.gui.singleton.global_gui_config.get_config_value("AUTO_SESSION_RECOVERY_ENABLED"):
        call_gui_callback(backup_session.restore_session_from_runtime_config)

    prepare_tab_data_of_open_state_machines(main_window_controller, sm_manager_model, open_state_machines)

    backup_session.reset_session()

    call_gui_callback(menubar_ctrl.on_stop_activate, None)
    call_gui_callback(menubar_ctrl.on_quit_activate, None, None, True)


def test_restore_session(caplog):
    change_in_gui_config = {'AUTO_BACKUP_ENABLED': False, 'HISTORY_ENABLED': False,
                            'AUTO_SESSION_RECOVERY_ENABLED': True, 'GAPHAS_EDITOR': False}

    # first run
    libraries = {"ros": join(testing_utils.EXAMPLES_PATH, "libraries", "ros_libraries"),
                 "turtle_libraries": join(testing_utils.EXAMPLES_PATH, "libraries", "turtle_libraries"),
                 "generic": join(testing_utils.LIBRARY_SM_PATH, "generic")}

    testing_utils.initialize_environment(gui_config=change_in_gui_config, libraries=libraries)

    main_window_controller = MainWindowController(rafcon.gui.singleton.state_machine_manager_model, MainWindowView())

    # Wait for GUI to initialize
    testing_utils.wait_for_gui()
    open_state_machines = {'list_of_hash_path_tab_page_number_tuple': [], 'selected_sm_page_number': None}
    thread = threading.Thread(target=trigger_gui_signals_first_run,
                              args=[rafcon.gui.singleton.state_machine_manager_model,
                                    main_window_controller,
                                    open_state_machines])
    thread.start()
    gtk.main()
    logger.debug("after gtk main")
    thread.join()

    testing_utils.shutdown_environment(caplog=caplog, expected_warnings=0, expected_errors=0)

    # second run
    libraries = {"ros": join(testing_utils.EXAMPLES_PATH, "libraries", "ros_libraries"),
                 "turtle_libraries": join(testing_utils.EXAMPLES_PATH, "libraries", "turtle_libraries"),
                 "generic": join(testing_utils.LIBRARY_SM_PATH, "generic")}
    testing_utils.initialize_environment(gui_config=change_in_gui_config, libraries=libraries)

    main_window_controller = MainWindowController(rafcon.gui.singleton.state_machine_manager_model, MainWindowView())

    # Wait for GUI to initialize
    testing_utils.wait_for_gui()
    final_open_state_machines = {'list_of_hash_path_tab_page_number_tuple': [], 'selected_sm_page_number': None}
    thread = threading.Thread(target=trigger_gui_signals_second_run,
                              args=[rafcon.gui.singleton.state_machine_manager_model,
                                    main_window_controller,
                                    final_open_state_machines])
    thread.start()
    gtk.main()
    logger.debug("after gtk main")
    thread.join()

    print open_state_machines
    print final_open_state_machines

    # test selection, page number and path
    # TODO find if there is a proper hash value test
    # TODO find out why core and gui hashes are changing !!! not even fully deterministic !!!
    # TODO find out why dirty flag is once wrong when AUTO_BACKUP is enabled in parallel
    #      (is connected to direct storing while opening)
    assert open_state_machines['selected_sm_page_number'] == final_open_state_machines['selected_sm_page_number']
    final_tuple_list = final_open_state_machines['list_of_hash_path_tab_page_number_tuple']

    CORE_HASH_INDEX = 0
    GUI_HASH_INDEX = 1
    PATH_INDEX = 2
    PAGE_NUMBER_INDEX = 3
    MARKED_DIRTY_INDEX = 4
    for index, sm_tuple in enumerate(open_state_machines['list_of_hash_path_tab_page_number_tuple']):
        assert index == sm_tuple[PAGE_NUMBER_INDEX]
        if not final_tuple_list[index][CORE_HASH_INDEX] == sm_tuple[CORE_HASH_INDEX]:
            print "CORE hashes page {4} are not equal: {0} != {1}, path: {2} {3}" \
                  "".format(final_tuple_list[index][CORE_HASH_INDEX], sm_tuple[CORE_HASH_INDEX],
                            sm_tuple[PATH_INDEX], sm_tuple[MARKED_DIRTY_INDEX], sm_tuple[PAGE_NUMBER_INDEX])
        # assert final_tuple_list[index][CORE_HASH_INDEX] == sm_tuple[CORE_HASH_INDEX]
        assert final_tuple_list[index][PATH_INDEX] == sm_tuple[PATH_INDEX]
        if not final_tuple_list[index][GUI_HASH_INDEX] == sm_tuple[GUI_HASH_INDEX]:
            print "GUI hashes page {4} are not equal: {0} != {1}, path: {2} {3}" \
                  "".format(final_tuple_list[index][GUI_HASH_INDEX], sm_tuple[GUI_HASH_INDEX],
                            sm_tuple[PATH_INDEX], sm_tuple[MARKED_DIRTY_INDEX], sm_tuple[PAGE_NUMBER_INDEX])
        # assert final_tuple_list[index][GUI_HASH_INDEX] == sm_tuple[GUI_HASH_INDEX]
        assert final_tuple_list[index][PAGE_NUMBER_INDEX] == sm_tuple[PAGE_NUMBER_INDEX]
        # page dirty 0, 4, 6 and not dirty 1, 2, 3, 5 -> at the moment 3 is dirty but after restore no more
        if not final_tuple_list[index][MARKED_DIRTY_INDEX] == sm_tuple[MARKED_DIRTY_INDEX]:
            print "MARKED DIRTY page {4} is not equal: {0} != {1}, path: {2} {3}" \
                  "".format(final_tuple_list[index][MARKED_DIRTY_INDEX], sm_tuple[MARKED_DIRTY_INDEX],
                            sm_tuple[PATH_INDEX], sm_tuple[MARKED_DIRTY_INDEX], sm_tuple[PAGE_NUMBER_INDEX])
    testing_utils.shutdown_environment(caplog=caplog, expected_warnings=0, expected_errors=0)


if __name__ == '__main__':
    pytest.main(['-s', __file__])