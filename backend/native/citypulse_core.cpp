#include <algorithm>
#include <cstddef>
#include <cmath>
#include <limits>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace {

struct Edge {
    int to;
    double cost;
    int road_index;
};

struct QueueItem {
    double cost;
    int node;
};

struct CompareQueueItem {
    bool operator()(const QueueItem& lhs, const QueueItem& rhs) const {
        return lhs.cost > rhs.cost;
    }
};

std::string trim(const std::string& value) {
    const auto begin = value.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) {
        return "";
    }
    const auto end = value.find_last_not_of(" \t\r\n");
    return value.substr(begin, end - begin + 1);
}

std::vector<std::string> split(const std::string& text, char delimiter) {
    std::vector<std::string> parts;
    std::stringstream stream(text);
    std::string item;
    while (std::getline(stream, item, delimiter)) {
        parts.push_back(item);
    }
    return parts;
}

std::string escape_join(const std::vector<std::string>& values, char delimiter) {
    std::ostringstream output;
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index > 0) {
            output << delimiter;
        }
        output << values[index];
    }
    return output.str();
}

}  // namespace

extern "C" {

__declspec(dllexport) const char* citypulse_core_version() {
    return "citypulse-core/0.1";
}

__declspec(dllexport) const char* citypulse_simulation_tick(
    const char* serialized_state,
    int seconds
) {
    static std::string response;
    try {
        if (serialized_state == nullptr || seconds <= 0) {
            throw std::runtime_error("state and positive seconds are required");
        }
        const std::vector<std::string> lines = split(serialized_state, '\n');
        if (lines.empty() || trim(lines[0]) != "CITYPULSE_STATE1") {
            throw std::runtime_error("invalid simulation state header");
        }
        double elapsed = 0.0;
        bool found_elapsed = false;
        for (std::size_t index = 1; index < lines.size(); ++index) {
            const std::vector<std::string> fields = split(trim(lines[index]), '|');
            if (fields.size() == 2 && fields[0] == "T") {
                elapsed = std::stod(fields[1]);
                found_elapsed = true;
                break;
            }
        }
        if (!found_elapsed) {
            throw std::runtime_error("elapsed time is missing");
        }
        std::ostringstream output;
        output << "OK|T|" << (elapsed + static_cast<double>(seconds));
        response = output.str();
        return response.c_str();
    } catch (const std::exception& error) {
        response = std::string("ERR|") + error.what();
        return response.c_str();
    }
}

__declspec(dllexport) const char* citypulse_simulation_tick_state(
    const char* serialized_state,
    int seconds
) {
    static std::string response;
    try {
        if (serialized_state == nullptr || seconds <= 0) {
            throw std::runtime_error("state and positive seconds are required");
        }
        const std::vector<std::string> lines = split(serialized_state, '\n');
        if (lines.empty() || trim(lines[0]) != "CITYPULSE_STATE1") {
            throw std::runtime_error("invalid simulation state header");
        }
        std::ostringstream output;
        output << "OK|STATE|CITYPULSE_STATE1\n";
        for (std::size_t index = 1; index < lines.size(); ++index) {
            const std::string line = trim(lines[index]);
            const std::vector<std::string> fields = split(line, '|');
            if (fields.size() == 2 && fields[0] == "T") {
                output << "T|" << (std::stod(fields[1]) + seconds) << "\n";
            } else if ((fields.size() == 5 || fields.size() == 6) && fields[0] == "V") {
                output << "V|" << fields[1] << "|" << fields[2] << "|" << fields[3]
                       << "|" << (std::stod(fields[4]) + seconds);
                if (fields.size() == 6) output << "|" << fields[5];
                output << "\n";
            } else if (fields.size() == 4 && fields[0] == "S") {
                double remaining = std::max(0.0, std::stod(fields[3]) - seconds);
                std::string phase = fields[2];
                if (remaining == 0.0) {
                    if (phase == "north_south") phase = "east_west";
                    else if (phase == "east_west") phase = "north_south";
                    remaining = 30.0;
                }
                output << "S|" << fields[1] << "|" << phase << "|" << remaining << "\n";
            }
        }
        response = output.str();
        return response.c_str();
    } catch (const std::exception& error) {
        response = std::string("ERR|") + error.what();
        return response.c_str();
    }
}

__declspec(dllexport) const char* citypulse_shortest_route(
    const char* serialized_network,
    const char* source_id,
    const char* destination_id
) {
    static std::string response;
    try {
        if (serialized_network == nullptr) {
            throw std::runtime_error("network payload is null");
        }

        std::vector<std::string> lines = split(serialized_network, '\n');
        if (lines.empty() || trim(lines[0]) != "CITYPULSE1") {
            throw std::runtime_error("invalid network header");
        }

        std::vector<std::string> intersections;
        std::vector<std::tuple<std::string, std::string, std::string, double>> road_rows;

        for (std::size_t index = 1; index < lines.size(); ++index) {
            const std::string line = trim(lines[index]);
            if (line.empty()) {
                continue;
            }
            const std::vector<std::string> fields = split(line, '|');
            if (fields.empty()) {
                continue;
            }

            if (fields[0] == "I" && fields.size() == 2) {
                intersections.push_back(fields[1]);
                continue;
            }
            if (fields[0] == "R" && fields.size() == 5) {
                road_rows.push_back(
                    std::make_tuple(fields[1], fields[2], fields[3], std::stod(fields[4]))
                );
                continue;
            }
            throw std::runtime_error("invalid network row");
        }

        if (source_id == nullptr || destination_id == nullptr) {
            throw std::runtime_error("route endpoints are missing");
        }
        const std::string source = source_id;
        const std::string destination = destination_id;

        std::vector<std::string> ids = intersections;
        for (const auto& row : road_rows) {
            if (std::find(ids.begin(), ids.end(), std::get<0>(row)) == ids.end()) {
                ids.push_back(std::get<0>(row));
            }
            if (std::find(ids.begin(), ids.end(), std::get<1>(row)) == ids.end()) {
                ids.push_back(std::get<1>(row));
            }
        }

        std::vector<std::vector<Edge>> adjacency(ids.size());
        auto find_node = [&ids](const std::string& node_id) -> int {
            for (std::size_t index = 0; index < ids.size(); ++index) {
                if (ids[index] == node_id) {
                    return static_cast<int>(index);
                }
            }
            return -1;
        };

        for (std::size_t road_index = 0; road_index < road_rows.size(); ++road_index) {
            const auto& row = road_rows[road_index];
            const int source = find_node(std::get<0>(row));
            const int destination = find_node(std::get<1>(row));
            if (source < 0 || destination < 0) {
                throw std::runtime_error("road references unknown intersection");
            }
            adjacency[source].push_back(Edge{destination, std::get<3>(row), static_cast<int>(road_index)});
        }

        const int source_index = find_node(source);
        const int destination_index = find_node(destination);
        if (source_index < 0 || destination_index < 0) {
            throw std::runtime_error("source or destination missing");
        }

        const double infinity = std::numeric_limits<double>::infinity();
        std::vector<double> distances(ids.size(), infinity);
        std::vector<int> previous_node(ids.size(), -1);
        std::vector<int> previous_road(ids.size(), -1);

        std::priority_queue<QueueItem, std::vector<QueueItem>, CompareQueueItem> queue;
        distances[source_index] = 0.0;
        queue.push(QueueItem{0.0, source_index});

        while (!queue.empty()) {
            const QueueItem current = queue.top();
            queue.pop();
            if (current.cost > distances[current.node]) {
                continue;
            }
            if (current.node == destination_index) {
                break;
            }

            for (const Edge& edge : adjacency[current.node]) {
                const double candidate = current.cost + edge.cost;
                if (candidate < distances[edge.to]) {
                    distances[edge.to] = candidate;
                    previous_node[edge.to] = current.node;
                    previous_road[edge.to] = edge.road_index;
                    queue.push(QueueItem{candidate, edge.to});
                }
            }
        }

        if (!std::isfinite(distances[destination_index])) {
            throw std::runtime_error("no route found");
        }

        std::vector<std::string> route_road_ids;
        std::vector<std::string> route_intersection_ids;
        int current = destination_index;
        route_intersection_ids.push_back(ids[current]);
        while (current != source_index) {
            const int road_index = previous_road[current];
            if (road_index < 0) {
                throw std::runtime_error("route reconstruction failed");
            }
            route_road_ids.push_back(std::get<2>(road_rows[road_index]));
            current = previous_node[current];
            route_intersection_ids.push_back(ids[current]);
        }
        std::reverse(route_road_ids.begin(), route_road_ids.end());
        std::reverse(route_intersection_ids.begin(), route_intersection_ids.end());

        std::ostringstream out;
        out << "OK|";
        out << source << "|";
        out << destination << "|";
        out << distances[destination_index] << "|";
        out << escape_join(route_road_ids, ',') << "|";
        out << escape_join(route_intersection_ids, ',');
        response = out.str();
        return response.c_str();
    } catch (const std::exception& error) {
        response = std::string("ERR|") + error.what();
        return response.c_str();
    }
}

}
