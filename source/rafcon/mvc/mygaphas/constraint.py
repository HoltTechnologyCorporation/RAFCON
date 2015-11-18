from rafcon.utils import log

logger = log.get_logger(__name__)

from gaphas.constraint import Constraint

from rafcon.mvc.mygaphas.items.ports import PortView
from rafcon.mvc.mygaphas.utils.enums import SnappedSide

from copy import deepcopy

EPSILON = 1e-6


def _update(variable, value):
    if abs(variable.value - value) > EPSILON:
        variable.value = value


class KeepRectangleWithinConstraint(Constraint):
    """Ensure that the children is within its parent

    Attributes:
     - parent_nw: NW coordinates of parent
     - parent_se: SE coordinates of parent
     - child_nw: NW coordinates of child
     - child_se: SE coordinates of child
    """

    def __init__(self, parent_nw, parent_se, child_nw, child_se, child=None, margin=None):
        super(KeepRectangleWithinConstraint, self).__init__(parent_nw[0], parent_nw[1], parent_se[0], parent_se[1],
                                                            child_nw[0], child_nw[1], child_se[0], child_se[1])
        self.parent_nw = parent_nw
        self.parent_se = parent_se
        self.child_nw = child_nw
        self.child_se = child_se
        self.child = child

        self.margin = margin
        min_margin = 0  # (parent_se[0].value - parent_nw[0].value) / 1000.
        if margin is None or margin < min_margin:
            self.margin = min_margin

    def solve_for(self, var=None):
        """
        Ensure that the children is within its parent
        """
        child_width = self.child_se[0].value - self.child_nw[0].value
        child_height = self.child_se[1].value - self.child_nw[1].value
        parent_width = self.parent_se[0].value - self.parent_nw[0].value
        parent_height = self.parent_se[1].value - self.parent_nw[1].value
        if child_width > parent_width - 2 * self.margin:
            child_width = parent_width - 2 * self.margin
        if child_height > parent_height - 2 * self.margin:
            child_height = parent_height - 2 * self.margin
        # Left edge (west)
        if self.parent_nw[0].value > self.child_nw[0].value - self.margin:
            _update(self.child_nw[0], self.parent_nw[0].value + self.margin)
            _update(self.child_se[0], self.child_nw[0].value + child_width)
        # Right edge (east)
        if self.parent_se[0].value < self.child_se[0].value + self.margin:
            _update(self.child_se[0], self.parent_se[0].value - self.margin)
            _update(self.child_nw[0], self.child_se[0].value - child_width)
        # Upper edge (north)
        if self.parent_nw[1].value > self.child_nw[1].value - self.margin:
            _update(self.child_nw[1], self.parent_nw[1].value + self.margin)
            _update(self.child_se[1], self.child_nw[1].value + child_height)
        # Lower edge (south)
        if self.parent_se[1].value < self.child_se[1].value + self.margin:
            _update(self.child_se[1], self.parent_se[1].value - self.margin)
            _update(self.child_nw[1], self.child_se[1].value - child_height)


class KeepPointWithinConstraint(KeepRectangleWithinConstraint):
    """Ensure that the children is within its parent

    Attributes:
     - parent_nw: NW coordinates of parent
     - parent_se: SE coordinates of parent
     - child_pos: coordinates of child
    """

    def __init__(self, parent_nw, parent_se, child_pos, margin=None):
        super(KeepPointWithinConstraint, self).__init__(parent_nw, parent_se, child_pos, child_pos)


class KeepRelativePositionConstraint(Constraint):
    def __init__(self, anchor, point):
        super(KeepRelativePositionConstraint, self).__init__(anchor[0], anchor[1], point[0], point[1])

        self.point = point
        self.anchor = anchor

        self._dx = point.x.value - anchor.x.value
        self._dy = point.y.value - anchor.y.value

    def solve_for(self, var):
        _update(self.point.x, self._dx + self.anchor.x)
        _update(self.point.y, self._dy + self.anchor.y)


class KeepPortDistanceConstraint(Constraint):
    def __init__(self, anchor, point, port, port_side_size, incoming):
        super(KeepPortDistanceConstraint, self).__init__(anchor[0], anchor[1], point[0], point[1])
        assert isinstance(port, PortView)

        self.distance = port_side_size

        self.incoming = incoming
        self.point = point
        self.anchor = anchor
        self.port = port

    def solve_for(self, var):
        distance = self.distance
        if self.port.side is SnappedSide.TOP:
            _update(self.point[0], self.anchor[0])
            _update(self.point[1],
                    self.anchor[1].value - distance if self.incoming else self.anchor[1].value + distance)
        elif self.port.side is SnappedSide.BOTTOM:
            _update(self.point[0], self.anchor[0])
            _update(self.point[1],
                    self.anchor[1].value + distance if self.incoming else self.anchor[1].value - distance)
        elif self.port.side is SnappedSide.LEFT:
            _update(self.point[0],
                    self.anchor[0].value - distance if self.incoming else self.anchor[0].value + distance)
            _update(self.point[1], self.anchor[1])
        elif self.port.side is SnappedSide.RIGHT:
            _update(self.point[0],
                    self.anchor[0].value + distance if self.incoming else self.anchor[0].value - distance)
            _update(self.point[1], self.anchor[1])


class PortRectConstraint(Constraint):
    """
    Keeps ports on rectangular path along containing state
    :param rect: Rect (NWpos, SEpos) specifying the path to bind port to
    :param point: Port position
    :param port: Port to bind
    """

    def __init__(self, rect, point, port):
        super(PortRectConstraint, self).__init__(rect[0][0], rect[0][1], rect[1][0], rect[1][1], point[0], point[1])

        self._rect = rect
        self._point = point
        self._initial_pos = deepcopy(point)
        self._port = port

        self._distance_to_border = self._port.port_side_size / 2.
        self.update_port_side()

    def update_port_side(self):
        """Updates the initial position of the port

        The port side is ignored but calculated from the port position. Then the port position is limited to the four
        side lines of the state.
        """
        from rafcon.utils.geometry import point_left_of_line

        p = (self._initial_pos.x, self._initial_pos.y)
        nw_x, nw_y, se_x, se_y = self.get_adjusted_border_positions()
        if point_left_of_line(p, (nw_x, nw_y), (se_x, se_y)):  # upper right triangle of state
            if point_left_of_line(p, (nw_x, se_y), (se_x, nw_y)):  # upper quarter triangle of state
                self._port.side = SnappedSide.TOP
                self.limit_pos(p[0], se_x, nw_x)
            else:  # right quarter triangle of state
                self._port.side = SnappedSide.RIGHT
                self.limit_pos(p[1], se_y, nw_y)
        else:  # lower left triangle of state
            if point_left_of_line(p, (nw_x, se_y), (se_x, nw_y)):  # left quarter triangle of state
                self._port.side = SnappedSide.LEFT
                self.limit_pos(p[1], se_y, nw_y)
            else:  # lower quarter triangle of state
                self._port.side = SnappedSide.BOTTOM
                self.limit_pos(p[0], se_x, nw_x)

        self.set_nearest_border()

    def solve_for(self, var=None):
        self._solve()

    def _solve(self):
        """
        Calculates the correct position of the port and keeps it aligned with the binding rect
        """

        # As the size of the containing state may has changed we need to update the distance to the border
        self.update_distance_to_border()
        px, py = self._point
        nw_x, nw_y, se_x, se_y = self.get_adjusted_border_positions()

        # If the port is located in one of the corners it is possible to move in two directions
        if ((self._initial_pos.x == nw_x and self._initial_pos.y == nw_y) or
                (self._initial_pos.x == se_x and self._initial_pos.y == nw_y) or
                (self._initial_pos.x == se_x and self._initial_pos.y == se_y) or
                (self._initial_pos.x == nw_x and self._initial_pos.y == se_y)):
            self.limit_pos(px, se_x, nw_x)
            self.limit_pos(py, se_y, nw_y)
        # If port movement starts at LEFT position, keep X position at place and move Y
        elif self._initial_pos.x == nw_x:
            _update(px, nw_x)
            self.limit_pos(py, se_y, nw_y)
            self._port.side = SnappedSide.LEFT
        # If port movement starts at TOP position, keep Y position at place and move X
        elif self._initial_pos.y == nw_y:
            _update(py, nw_y)
            self.limit_pos(px, se_x, nw_x)
            self._port.side = SnappedSide.TOP
        # If port movement starts at RIGHT position, keep X position at place and move Y
        elif self._initial_pos.x == se_x:
            _update(px, se_x)
            self.limit_pos(py, se_y, nw_y)
            self._port.side = SnappedSide.RIGHT
        # If port movement starts at BOTTOM position, keep Y position at place and move X
        elif self._initial_pos.y == se_y:
            _update(py, se_y)
            self.limit_pos(px, se_x, nw_x)
            self._port.side = SnappedSide.BOTTOM
        # If containing state has been resized, snap ports accordingly to border
        else:
            self.set_nearest_border()

        # Update initial position for next reference
        _update(self._initial_pos.x, deepcopy(px.value))
        _update(self._initial_pos.y, deepcopy(py.value))

    def update_distance_to_border(self):
        self._distance_to_border = self._port.port_side_size / 2.

    @staticmethod
    def limit_pos(p, se_pos, nw_pos):
        """
        Limits position p to stay inside containing state
        :param p: Position to limit
        :param se_pos: Bottom/Right boundary
        :param nw_pos: Top/Left boundary
        :return:
        """
        if p > se_pos:
            _update(p, se_pos)
        elif p < nw_pos:
            _update(p, nw_pos)

    def get_adjusted_border_positions(self):
        """
        Calculates the positions to limit the port movement to
        :return: Adjusted positions nw_x, nw_y, se_x, se_y
        """
        nw_x, nw_y = self._rect[0]
        se_x, se_y = self._rect[1]

        nw_x += self._distance_to_border
        nw_y += self._distance_to_border
        se_x -= self._distance_to_border
        se_y -= self._distance_to_border

        return nw_x, nw_y, se_x, se_y

    def set_nearest_border(self):
        """Snaps the port to the correct side upon state size change
        """
        px, py = self._point
        nw_x, nw_y, se_x, se_y = self.get_adjusted_border_positions()

        if self._port.side == SnappedSide.RIGHT:
            _update(px, se_x)
        elif self._port.side == SnappedSide.BOTTOM:
            _update(py, se_y)
        elif self._port.side == SnappedSide.LEFT:
            _update(px, nw_x)
        elif self._port.side == SnappedSide.TOP:
            _update(py, nw_y)
