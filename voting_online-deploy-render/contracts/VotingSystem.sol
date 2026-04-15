// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract VotingSystem {
    address public owner;

    constructor() {
        owner = msg.sender;
        nextCandidateId = 1;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    // =========================
    // STRUCTS
    // =========================

    struct Candidate {
        uint id;
        string name;
        string description;
        string imageUrl;
    }

    struct Election {
        string name;
        uint[] candidateIds;
        bool isActive;
        mapping(address => bool) hasVoted;
        mapping(uint => uint) voteCounts;
    }

    // =========================
    // STORAGE
    // =========================

    uint public nextCandidateId;

    mapping(uint => Candidate) public candidates;

    // ❗ FIX: để private để tránh lỗi getter với mapping trong struct
    mapping(bytes32 => Election) private elections;

    // =========================
    // EVENTS
    // =========================

    event CandidateAdded(uint indexed candidateId, string name);
    event ElectionCreated(bytes32 indexed electionCode, string name);
    event ElectionStatusChanged(bytes32 indexed electionCode, bool status);
    event Voted(bytes32 indexed electionCode, address indexed voter, uint indexed candidateId);

    // =========================
    // ADMIN
    // =========================

    function addCandidate(
        string memory _name,
        string memory _description,
        string memory _imageUrl
    ) external onlyOwner {
        require(bytes(_name).length > 0, "Empty name");

        candidates[nextCandidateId] = Candidate(
            nextCandidateId,
            _name,
            _description,
            _imageUrl
        );

        emit CandidateAdded(nextCandidateId, _name);
        nextCandidateId++;
    }

    function createElection(
        bytes32 _code,
        string memory _name,
        uint[] memory _candidateIds
    ) external onlyOwner {
        require(bytes(_name).length > 0, "Empty name");
        require(_candidateIds.length > 0, "No candidates");

        Election storage e = elections[_code];
        require(e.candidateIds.length == 0, "Election exists");

        // check candidate hợp lệ
        for (uint i = 0; i < _candidateIds.length; i++) {
            require(candidates[_candidateIds[i]].id != 0, "Invalid candidate");
        }

        e.name = _name;
        e.candidateIds = _candidateIds;
        e.isActive = true;

        emit ElectionCreated(_code, _name);
    }

    function toggleElectionStatus(bytes32 _code, bool _status) external onlyOwner {
        require(elections[_code].candidateIds.length > 0, "Not exist");

        elections[_code].isActive = _status;

        emit ElectionStatusChanged(_code, _status);
    }

    // =========================
    // USER
    // =========================

    function vote(bytes32 _code, uint _candidateId) external {
        Election storage e = elections[_code];

        require(e.candidateIds.length > 0, "Election not exist");
        require(e.isActive, "Election not active");
        require(!e.hasVoted[msg.sender], "Already voted");

        bool valid = false;
        for (uint i = 0; i < e.candidateIds.length; i++) {
            if (e.candidateIds[i] == _candidateId) {
                valid = true;
                break;
            }
        }

        require(valid, "Candidate not in election");

        e.voteCounts[_candidateId]++;
        e.hasVoted[msg.sender] = true;

        emit Voted(_code, msg.sender, _candidateId);
    }

    // =========================
    // VIEW
    // =========================

    function getCandidate(uint _id)
        external
        view
        returns (
            uint,
            string memory,
            string memory,
            string memory
        )
    {
        Candidate storage c = candidates[_id];
        require(c.id != 0, "Not exist");

        return (c.id, c.name, c.description, c.imageUrl);
    }

    function getElectionDetails(bytes32 _code)
        external
        view
        returns (
            string memory,
            bool,
            uint[] memory
        )
    {
        Election storage e = elections[_code];
        require(e.candidateIds.length > 0, "Not exist");

        return (e.name, e.isActive, e.candidateIds);
    }

    function getCandidateVoteCount(bytes32 _code, uint _candidateId)
        external
        view
        returns (uint)
    {
        require(elections[_code].candidateIds.length > 0, "Not exist");

        return elections[_code].voteCounts[_candidateId];
    }

    function hasVotedInElection(bytes32 _code, address _user)
        external
        view
        returns (bool)
    {
        require(elections[_code].candidateIds.length > 0, "Not exist");

        return elections[_code].hasVoted[_user];
    }
}