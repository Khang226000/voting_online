// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract VotingSystem {
    address public owner;

    // Struct để lưu thông tin ứng viên
    struct Candidate {
        uint id;
        string name;
        string description;
        string imageUrl; // URL ảnh, có thể lưu trên IPFS hoặc server
    }

    // Struct để lưu thông tin cuộc bầu cử
    struct Election {
        string name;
        uint[] candidateIds; // Danh sách ID ứng viên tham gia cuộc bầu cử này
        bool isActive; // Trạng thái hoạt động của cuộc bầu cử
        mapping(address => bool) hasVoted; // Kiểm tra xem địa chỉ đã bỏ phiếu trong cuộc bầu cử này chưa
        mapping(uint => uint) voteCounts; // Số phiếu cho từng ứng viên trong cuộc bầu cử này (candidateId => count)
    }

    // Mapping lưu trữ tất cả ứng viên theo ID
    mapping(uint => Candidate) public candidates;
    uint public nextCandidateId; // ID tiếp theo cho ứng viên mới

    // Mapping lưu trữ tất cả cuộc bầu cử theo mã bầu cử (bytes32)
    mapping(bytes32 => Election) public elections;

    // Events để thông báo các hành động quan trọng
    event CandidateAdded(uint indexed candidateId, string name);
    event ElectionCreated(bytes32 indexed electionCode, string name);
    event ElectionStatusChanged(bytes32 indexed electionCode, bool newStatus);
    event Voted(bytes32 indexed electionCode, address indexed voter, uint indexed candidateId);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }

    constructor() {
        owner = msg.sender;
        nextCandidateId = 1; // Bắt đầu ID ứng viên từ 1
    }

    // =========================
    // ADMIN FUNCTIONS (Chỉ chủ sở hữu hợp đồng mới có thể gọi)
    // =========================

    /// @notice Thêm một ứng viên mới vào hệ thống
    /// @param _name Tên của ứng viên
    /// @param _description Mô tả về ứng viên
    /// @param _imageUrl URL hình ảnh của ứng viên
    function addCandidate(string memory _name, string memory _description, string memory _imageUrl) public onlyOwner {
        require(bytes(_name).length > 0, "Candidate name cannot be empty");
        candidates[nextCandidateId] = Candidate(nextCandidateId, _name, _description, _imageUrl);
        emit CandidateAdded(nextCandidateId, _name);
        nextCandidateId++;
    }

    /// @notice Tạo một cuộc bầu cử mới
    /// @param _electionCode Mã định danh duy nhất cho cuộc bầu cử (ví dụ: "VOTE2024")
    /// @param _name Tên của cuộc bầu cử
    /// @param _candidateIds Danh sách ID của các ứng viên tham gia cuộc bầu cử này
    function createElection(bytes32 _electionCode, string memory _name, uint[] memory _candidateIds) public onlyOwner {
        require(bytes(_name).length > 0, "Election name cannot be empty");
        require(_candidateIds.length > 0, "Election must have at least one candidate");
        require(elections[_electionCode].candidateIds.length == 0, "Election code already exists"); // Kiểm tra mã bầu cử chưa tồn tại

        // Kiểm tra tất cả candidateIds có hợp lệ không
        for (uint i = 0; i < _candidateIds.length; i++) {
            require(candidates[_candidateIds[i]].id != 0, "Invalid candidate ID provided");
        }

        elections[_electionCode].name = _name;
        elections[_electionCode].candidateIds = _candidateIds;
        elections[_electionCode].isActive = true; // Mặc định là hoạt động khi tạo
        
        emit ElectionCreated(_electionCode, _name);
    }

    /// @notice Thay đổi trạng thái hoạt động của một cuộc bầu cử (kích hoạt/ngừng kích hoạt)
    /// @param _electionCode Mã của cuộc bầu cử
    /// @param _status Trạng thái mới (true để kích hoạt, false để ngừng kích hoạt)
    function toggleElectionStatus(bytes32 _electionCode, bool _status) public onlyOwner {
        require(elections[_electionCode].candidateIds.length > 0, "Election does not exist");
        elections[_electionCode].isActive = _status;
        emit ElectionStatusChanged(_electionCode, _status);
    }

    // =========================
    // USER FUNCTIONS (Chức năng dành cho người dùng)
    // =========================

    /// @notice Bỏ phiếu cho một ứng viên trong một cuộc bầu cử cụ thể
    /// @param _electionCode Mã của cuộc bầu cử
    /// @param _candidateId ID của ứng viên muốn bỏ phiếu
    function vote(bytes32 _electionCode, uint _candidateId) public {
        Election storage election = elections[_electionCode];

        require(election.candidateIds.length > 0, "Election does not exist");
        require(election.isActive, "Election is not active");
        require(!election.hasVoted[msg.sender], "You have already voted in this election");

        bool candidateFound = false;
        for (uint i = 0; i < election.candidateIds.length; i++) {
            if (election.candidateIds[i] == _candidateId) {
                candidateFound = true;
                break;
            }
        }
        require(candidateFound, "Candidate is not part of this election");

        election.voteCounts[_candidateId]++;
        election.hasVoted[msg.sender] = true;

        emit Voted(_electionCode, msg.sender, _candidateId);
    }

    // =========================
    // VIEW FUNCTIONS (Chức năng chỉ đọc dữ liệu, không tốn gas)
    // =========================

    /// @notice Lấy thông tin chi tiết của một ứng viên
    /// @param _candidateId ID của ứng viên
    /// @return id, name, description, imageUrl
    function getCandidate(uint _candidateId) public view returns (uint id, string memory name, string memory description, string memory imageUrl) {
        Candidate storage c = candidates[_candidateId];
        require(c.id != 0, "Candidate does not exist");
        return (c.id, c.name, c.description, c.imageUrl);
    }

    /// @notice Lấy thông tin chi tiết của một cuộc bầu cử
    /// @param _electionCode Mã của cuộc bầu cử
    /// @return name, isActive, candidateIds
    function getElectionDetails(bytes32 _electionCode) public view returns (string memory name, bool isActive, uint[] memory candidateIds) {
        Election storage election = elections[_electionCode];
        require(election.candidateIds.length > 0, "Election does not exist");
        return (election.name, election.isActive, election.candidateIds);
    }

    /// @notice Lấy số phiếu bầu của một ứng viên trong một cuộc bầu cử cụ thể
    /// @param _electionCode Mã của cuộc bầu cử
    /// @param _candidateId ID của ứng viên
    /// @return Số phiếu bầu của ứng viên
    function getCandidateVoteCount(bytes32 _electionCode, uint _candidateId) public view returns (uint) {
        Election storage election = elections[_electionCode];
        require(election.candidateIds.length > 0, "Election does not exist");
        // Nếu ứng viên không có phiếu hoặc không thuộc cuộc bầu cử, sẽ trả về 0
        return election.voteCounts[_candidateId];
    }

    /// @notice Kiểm tra xem một địa chỉ đã bỏ phiếu trong một cuộc bầu cử cụ thể chưa
    /// @param _electionCode Mã của cuộc bầu cử
    /// @param _voter Địa chỉ của người bỏ phiếu
    /// @return true nếu đã bỏ phiếu, false nếu chưa
    function hasVotedInElection(bytes32 _electionCode, address _voter) public view returns (bool) {
        Election storage election = elections[_electionCode];
        require(election.candidateIds.length > 0, "Election does not exist");
        return election.hasVoted[_voter];
    }
}