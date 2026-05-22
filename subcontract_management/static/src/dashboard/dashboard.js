/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
const { Component, useState, onWillStart } = owl;

export class SubcontractDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        
        this.state = useState({
            stats: {
                total_projects: 0,
                active_tasks: 0,
                avg_oee: 0,
                total_profit: 0
            },
            delayed_tasks: []
        });

        onWillStart(async () => {
            await this.fetchDashboardData();
        });
    }

    async fetchDashboardData() {
        // Fetch Projects Stat
        const projects = await this.orm.searchRead('subcontract.project', [], ['net_profit']);
        const totalProfit = projects.reduce((acc, p) => acc + p.net_profit, 0);

        // Fetch Tasks Stat
        const tasks = await this.orm.searchRead('subcontract.task', [], ['state', 'oee_total', 'deadline', 'name', 'project_id', 'vendor_id']);
        const activeTasks = tasks.filter(t => ['assigned', 'in_progress'].includes(t.state));
        
        // Calculate average OEE
        const oeeSum = tasks.reduce((acc, t) => acc + t.oee_total, 0);
        const avgOEE = tasks.length ? oeeSum / tasks.length : 0;

        // Find Delayed Tasks (deadline < today)
        const today = new Date().toISOString().split('T')[0];
        const delayedTasks = activeTasks.filter(t => t.deadline && t.deadline < today);

        this.state.stats = {
            total_projects: projects.length,
            active_tasks: activeTasks.length,
            avg_oee: avgOEE,
            total_profit: totalProfit
        };
        this.state.delayed_tasks = delayedTasks;
    }
}

SubcontractDashboard.template = "subcontract_dashboard";

// Register the component to the action registry
registry.category("actions").add("subcontract_dashboard_main", SubcontractDashboard);
