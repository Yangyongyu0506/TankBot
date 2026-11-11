"""已知地图全局规划算法；此文件全部属于玩家，跨关和升级保留。"""
import numpy as np
from numpy.typing import NDArray
from tankbot import OccupancyGrid


class GlobalPlanner:
    def __init__(
        self,
        map_data: OccupancyGrid,
        robot_radius_m: float,
        safety_margin_m: float,
    ) -> None:
        """只收到公开原始地图、车体外接圆半径和安全余量。

        map_data.grid: 只读bool (H,W)，True障碍、False自由，没有未知格。
        map_data.origin_xy: 只读float64 (2,)，左下角格的左下角，map系米。
        map_data.resolution_m: 每格边长，米；行向+y、列向+x。
        map_data.world_to_grid(xy): 地图[x,y] -> (row,col)，向下取整。
        map_data.grid_to_world(row,col): 该格中心的只读float64 [x,y]。
        越界明确报错；需要工作副本时使用map_data.grid.copy()。
        自行实现方形膨胀：ceil((半径+余量)/分辨率)格，场地外也按障碍。
        构造、导入、搜索、后处理及结果往返都在独立5秒规划截止内。
        """
        self.map_data: OccupancyGrid = map_data
        self.robot_radius_m: float = robot_radius_m
        self.safety_margin_m: float = safety_margin_m

    def plan(
        self,
        start_xy: NDArray[np.float64],
        goal_xy: NDArray[np.float64],
    ) -> NDArray[np.float64] | None:
        """自行实现膨胀、邻居生成、搜索、后处理和重采样。

        start_xy/goal_xy: 只读float64 (2,)地图系绝对米制坐标[x,y]。
        找到路径返回float64 (N,2)，2<=N<=512，从起点到终点排序；
        首尾距离容差1e-6m，每段>1e-6m且<=0.10m+1e-6m。
        返回的是绝对[x,y]，不是格索引或相对位移；中间点不必为格中心。
        节点及整段均不得进入/接触规范膨胀区域；不能斜穿障碍格角。
        不要求最短路、固定转弯半径或逐点停车；框架不会修补或平滑路径。
        确认无解返回None，错误保留异常；正式任务保证可达，None会失败。
        规划通过后，既有PathFollower/轮控实际驾驶；本函数运行中不再调用。
        折线拐角可能需要你后处理或调整既有跟踪器。
        """
        return None
