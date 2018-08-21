# Copyright

# example basictreeview.py

import gtk
import shelve

import rafcon.utils.execution_log as log_helper
from rafcon.gui.controllers.utils.extended_controller import ExtendedController

from rafcon.utils import log

logger = log.get_logger(__name__)


class ExecutionLogTreeController(ExtendedController):

    RUN_ID_STORAGE_ID = 1

    def __init__(self, model, view, filename, run_id_to_select):

        logger.verbose("Select run_id: {0}".format(run_id_to_select))
        super(ExecutionLogTreeController, self).__init__(model, view)

        self.run_id_to_select = run_id_to_select
        self.hist_items = shelve.open(filename, 'r')
        self.start, self.next_, self.concurrent, self.hierarchy, self.items = \
            log_helper.log_to_collapsed_structure(self.hist_items,
                                                  throw_on_pickle_error=False,
                                                  include_erroneous_data_ports=True)
        # create a TreeStore with one string column to use as the model
        self.tree_store = gtk.TreeStore(str, str)
        self.item_iter = {}
        view.tree_view.set_model(self.tree_store)

    def register_view(self, view):

        # we'll add some data now - 4 rows with 3 child rows each
        if not self.start:
            logger.warning('WARNING: no start item found, just listing all items')
            elements = [(None, run_id) for run_id in self.items.keys()]
        else:
            elements = [(None, self.start['run_id'])]

        while True:
            new_elements = []
            for e in elements:
                item_tuple = self.add_collapsed_key(e[0], e[1])
                new_elements.extend(item_tuple)
            if len(new_elements) == 0:
                break
            else:
                elements = new_elements

        view.tree_view.get_selection().connect('changed', self.on_treeview_selection_changed)

        # optional select a element of generated tree
        if self.run_id_to_select in self.item_iter:
            item_iter_to_select = self.item_iter[self.run_id_to_select]
            path_to_select = self.tree_store.get_path(item_iter_to_select)
            self.view.tree_view.expand_to_path(path_to_select)
            self.view.tree_view.get_selection().select_iter(item_iter_to_select)
            self.run_id_to_select = None

    def add_collapsed_key(self, parent, key):
        parent_iter = self.tree_store.append(parent, ["%s (%s)" % (self.items[key]['state_name'], self.items[key]['state_type']), str(key)])
        self.item_iter[key] = parent_iter

        returns = []
        if key in self.next_:
            # self.add_collapsed_key(parent, self.next_[key])
            returns.append((parent, self.next_[key]))

        if key in self.hierarchy:
            # self.add_collapsed_key(piter, self.hierarchy[key])
            returns.append((parent_iter, self.hierarchy[key]))

        if key in self.concurrent:
            for i, next_key in enumerate(self.concurrent[key]):
                child_iter = self.tree_store.append(parent_iter, [str(i), None])
                # self.add_collapsed_key(child_iter, next_key)
                returns.append((child_iter, next_key))
                self.item_iter[key] = child_iter

        return returns

    def add_key(self, parent, key):
        parent_iter = self.tree_store.append(parent, [str(key)])
        self.item_iter[key] = parent_iter

        if key in self.next_ and self.items[key]['call_type'] == 'EXECUTE':
            self.add_key(parent, self.next_[key])
        elif key in self.next_ and self.items[key]['call_type'] == 'CONTAINER' and (self.items[key]['item_type'] == 'CallItem'):
            self.add_key(parent_iter, self.next_[key])
        if key in self.next_ and self.items[key]['call_type'] == 'CONTAINER' and (self.items[key]['item_type'] == 'ConcurrencyItem'):
            self.add_key(parent, self.next_[key])
        elif key in self.next_ and self.items[key]['call_type'] == 'CONTAINER' and self.items[key]['item_type'] == 'ReturnItem':
            new_parent = self.tree_store.iter_parent(parent)
            self.add_key(new_parent, self.next_[key])

        if key in self.concurrent:
            for i, next_key in enumerate(self.concurrent[key]):
                child_iter = self.tree_store.append(parent_iter, [str(i)])
                self.add_key(child_iter, next_key)

    def on_treeview_selection_changed(self, tree_selection):
        m, selected_tree_item_iter = tree_selection.get_selected()
        hist_item_id = m.get_value(selected_tree_item_iter, self.RUN_ID_STORAGE_ID)
        item = self.items.get(hist_item_id)
        import pprint as pp
        self.view.text_view.get_buffer().set_text(pp.pformat(item))
