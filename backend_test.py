import requests
import sys
import json
from datetime import datetime
import time

class PortSystemAPITester:
    def __init__(self, base_url="https://harborlink.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})

    def run_test(self, name, method, endpoint, expected_status, data=None, timeout=30):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}" if endpoint else f"{self.api_url}/"
        
        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = self.session.get(url, timeout=timeout)
            elif method == 'POST':
                response = self.session.post(url, json=data, timeout=timeout)
            elif method == 'PUT':
                response = self.session.put(url, json=data, timeout=timeout)
            elif method == 'DELETE':
                response = self.session.delete(url, timeout=timeout)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    if isinstance(response_data, dict) and len(response_data) <= 3:
                        print(f"   Response: {response_data}")
                    elif isinstance(response_data, list):
                        print(f"   Response: List with {len(response_data)} items")
                    else:
                        print(f"   Response: {type(response_data).__name__} data received")
                except:
                    print(f"   Response: Non-JSON response")
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text[:200]}")

            return success, response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text

        except requests.exceptions.Timeout:
            print(f"❌ Failed - Request timeout after {timeout}s")
            return False, {}
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test API root endpoint"""
        return self.run_test("API Root", "GET", "", 200)

    def test_get_vessels(self):
        """Test get all vessels"""
        return self.run_test("Get Vessels", "GET", "vessels", 200)

    def test_get_berth_timeline(self):
        """Test get berth timeline for Gantt chart"""
        return self.run_test("Get Berth Timeline", "GET", "berths/timeline", 200)

    def test_get_conflicts(self):
        """Test get conflicts"""
        return self.run_test("Get Conflicts", "GET", "conflicts", 200)

    def test_get_kpis(self):
        """Test get KPIs"""
        return self.run_test("Get KPIs", "GET", "kpis", 200)

    def test_sync_external_data(self):
        """Test sync external data - this is the core integration test"""
        print("\n🚢 Testing External API Integration (this may take longer)...")
        return self.run_test("Sync External Data", "POST", "sync-external-data", 200, timeout=60)

    def test_get_specific_vessel(self):
        """Test get specific vessel (first get vessels, then test specific one)"""
        success, vessels_data = self.test_get_vessels()
        if success and isinstance(vessels_data, list) and len(vessels_data) > 0:
            vessel_id = vessels_data[0].get('identificador_navio')
            if vessel_id:
                return self.run_test(f"Get Specific Vessel ({vessel_id})", "GET", f"vessels/{vessel_id}", 200)
        
        print("⚠️  Skipping specific vessel test - no vessels available")
        return True, {}

    def test_kpis_with_date_range(self):
        """Test KPIs with date range parameters"""
        start_date = "2024-01-01T00:00:00"
        end_date = "2024-12-31T23:59:59"
        endpoint = f"kpis?start_date={start_date}&end_date={end_date}"
        return self.run_test("Get KPIs with Date Range", "GET", endpoint, 200)

def main():
    print("🚢 Hub de Atracação - Porto de Santos API Testing")
    print("=" * 60)
    
    # Setup
    tester = PortSystemAPITester()
    
    # Test sequence
    print("\n📋 Running Backend API Tests...")
    
    # Basic connectivity tests
    tester.test_root_endpoint()
    
    # Core data retrieval tests
    tester.test_get_vessels()
    tester.test_get_berth_timeline()
    tester.test_get_conflicts()
    tester.test_get_kpis()
    tester.test_kpis_with_date_range()
    
    # Test specific vessel endpoint
    tester.test_get_specific_vessel()
    
    # Critical integration test - sync external data
    tester.test_sync_external_data()
    
    # Re-test data endpoints after sync to see if data was populated
    print("\n🔄 Re-testing data endpoints after sync...")
    tester.test_get_vessels()
    tester.test_get_berth_timeline()
    tester.test_get_conflicts()
    tester.test_get_kpis()

    # Print results
    print(f"\n📊 Test Results Summary:")
    print(f"Tests passed: {tester.tests_passed}/{tester.tests_run}")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All backend tests passed!")
        return 0
    else:
        print(f"⚠️  {tester.tests_run - tester.tests_passed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())