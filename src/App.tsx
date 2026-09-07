import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '@/context/AuthContext';
import { DataProvider } from '@/context/DataContext';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { AppLayout } from '@/components/layout/AppLayout';

import Login from '@/pages/Login';
import Signup from '@/pages/Signup';
import Dashboard from '@/pages/Dashboard';
import Devices from '@/pages/Devices';
import WorkflowCreate from '@/pages/WorkflowCreate';
import WorkflowBuilder from '@/pages/WorkflowBuilder';
import WorkflowExecuteInput from '@/pages/WorkflowExecuteInput';
import ExecutionResult from '@/pages/ExecutionResult';
import Executions from '@/pages/Executions';
import DataSources from '@/pages/DataSources';
import Marketplace from '@/pages/Marketplace';
import EventLog from '@/pages/EventLog';
import SettingsPage from '@/pages/Settings';

export default function App() {
  return (
    <AuthProvider>
      <DataProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />

            <Route
              element={
                <ProtectedRoute>
                  <AppLayout />
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<Dashboard />} />
              <Route path="/devices" element={<Devices />} />
              <Route path="/workflows/new" element={<WorkflowCreate />} />
              <Route path="/workflows/:id" element={<WorkflowBuilder />} />
              <Route path="/workflows/:id/run" element={<WorkflowExecuteInput />} />
              <Route path="/executions" element={<Executions />} />
              <Route path="/executions/:id" element={<ExecutionResult />} />
              <Route path="/data-sources" element={<DataSources />} />
              <Route path="/marketplace" element={<Marketplace />} />
              <Route path="/events" element={<EventLog />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </DataProvider>
    </AuthProvider>
  );
}
